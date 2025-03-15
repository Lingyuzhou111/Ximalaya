# encoding:utf-8
import json
import requests
import re
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *

@plugins.register(
    name="Ximalaya",
    desire_priority=100,
    desc="喜马拉雅音频搜索插件，支持以下功能：\n1. 搜索有声剧：xm搜索 [剧名] [n]\n2. 获取剧集列表：xm专辑 [专辑ID] [n]\n3. 点播音频：xm点播 [专辑ID] [序号]",
    version="1.1",
    author="Lingyuzhou",
)
class Ximalaya(Plugin):
    # 常量定义
    API_BASE_URL = "https://hhlqilongzhu.cn/api/ximalaya/ximalaya.php"
    DEFAULT_COVER = "https://imagev2.xmcdn.com/group68/M06/CA/C5/wKgMbl3h6ymBhuY6AAQ8GGO2hg8567.jpg"
    DEFAULT_RESULTS = 5  # 默认显示结果数量
    DEFAULT_ALBUM_RESULTS = 10  # 专辑列表默认显示结果数量
    
    # 新的触发词和指令格式
    SEARCH_TRIGGER = "xm搜索"  # 搜索有声剧
    ALBUM_TRIGGER = "xm专辑"   # 获取专辑信息
    PLAY_TRIGGER = "xm点播"    # 点播音频
    
    def __init__(self):
        super().__init__()
        self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
        logger.info("[Ximalaya] inited.")

    def on_handle_context(self, e_context: EventContext):
        """处理用户消息的主函数"""
        content = e_context["context"].content
        reply = None
        
        # 处理搜索指令：xm搜索 剧名 n
        if content.startswith(self.SEARCH_TRIGGER):
            query = content[len(self.SEARCH_TRIGGER):].strip()
            # 提取剧名和结果数量
            match = re.match(r'^(.*?)(?:\s+(\d+))?$', query)
            if match:
                keyword, count_str = match.groups()
                count = int(count_str) if count_str else self.DEFAULT_RESULTS
                reply = self._search_audio(keyword.strip(), count)
        
        # 处理专辑指令：xm专辑 albumId n
        elif content.startswith(self.ALBUM_TRIGGER):
            query = content[len(self.ALBUM_TRIGGER):].strip()
            # 提取专辑ID和结果数量
            match = re.match(r'^(\d+)(?:\s+(\d+))?$', query)
            if match:
                album_id, count_str = match.groups()
                count = int(count_str) if count_str else self.DEFAULT_ALBUM_RESULTS
                reply = self._get_album_info(album_id, count)
        
        # 处理点播指令：xm点播 albumId 序号
        elif content.startswith(self.PLAY_TRIGGER):
            query = content[len(self.PLAY_TRIGGER):].strip()
            # 提取专辑ID和序号
            match = re.match(r'^(\d+)(?:\s+(\d+))?$', query)
            if match:
                album_id, episode_number_str = match.groups()
                episode_number = int(episode_number_str) if episode_number_str else 1  # 默认第一集
                reply = self._get_episode_with_number(album_id, episode_number)
        
        if reply:
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
        
        return

    def _create_text_reply(self, content):
        """创建文本回复对象"""
        reply = Reply()
        reply.type = ReplyType.TEXT
        reply.content = content
        return reply

    def _create_app_reply(self, content):
        """创建应用消息回复对象"""
        reply = Reply()
        reply.type = ReplyType.APP
        reply.content = content
        return reply

    def _api_request(self, params):
        """统一API请求函数"""
        try:
            response = requests.get(self.API_BASE_URL, params=params)
            return response.json()
        except Exception as e:
            logger.error(f"[Ximalaya] API request error: {str(e)}")
            return None

    def _construct_music_appmsg(self, title, music_url, thumb_url, author):
        """构建音乐卡片XML消息"""
        # 处理封面URL
        thumb_url_xml = self._process_image_url(thumb_url)
        
        # 处理音频URL的XML转义
        music_url_xml = self._escape_xml(music_url)

        # 构建XML消息
        xml = f"""<appmsg appid="" sdkver="0">
    <title>{title}</title>
    <des>{author}</des>
    <action>view</action>
    <type>3</type>
    <showtype>0</showtype>
    <soundtype>0</soundtype>
    <mediatagname>音频</mediatagname>
    <messageaction></messageaction>
    <content></content>
    <contentattr>0</contentattr>
    <url>{music_url_xml}</url>
    <lowurl>{music_url_xml}</lowurl>
    <dataurl>{music_url_xml}</dataurl>
    <lowdataurl>{music_url_xml}</lowdataurl>
    <appattach>
        <totallen>0</totallen>
        <attachid></attachid>
        <emoticonmd5></emoticonmd5>
        <cdnthumburl>{thumb_url_xml}</cdnthumburl>
        <cdnthumbaeskey></cdnthumbaeskey>
        <aeskey></aeskey>
    </appattach>
    <extinfo></extinfo>
    <sourceusername></sourceusername>
    <sourcedisplayname>喜马拉雅</sourcedisplayname>
    <thumburl>{thumb_url_xml}</thumburl>
    <songalbumurl>{thumb_url_xml}</songalbumurl>
    <songlyric></songlyric>
    <appname>喜马拉雅</appname>
    <musictype>0</musictype>
</appmsg>"""
        return xml

    def _process_image_url(self, thumb_url):
        """处理图片URL，确保格式正确并可访问"""
        if not thumb_url:
            return self._escape_xml(self.DEFAULT_COVER)
            
        # 确保URL是以https开头
        if not thumb_url.startswith(("http://", "https://")):
            thumb_url = "https://" + thumb_url.lstrip("/")
        elif thumb_url.startswith("http://"):
            # 将http转为https
            thumb_url = "https://" + thumb_url[7:]
        
        # 简化URL，去除特殊格式
        if "!" in thumb_url:
            thumb_url = thumb_url.split("!")[0]
        
        # 验证URL的合法性
        try:
            for _ in range(3):  # 最多重试3次
                try:
                    response = requests.head(thumb_url, timeout=5)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    continue
            else:  # 所有重试都失败
                logger.warning(f"[Ximalaya] 封面图片URL无效: {thumb_url}")
                return self._escape_xml(self.DEFAULT_COVER)
        except Exception as e:
            logger.error(f"[Ximalaya] 验证封面图片URL出错: {str(e)}")
            return self._escape_xml(self.DEFAULT_COVER)
        
        # 处理URL中的特殊字符（XML转义）
        return self._escape_xml(thumb_url)

    def _escape_xml(self, text):
        """转义XML特殊字符"""
        if not text:
            return ""
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;").replace('"', "&quot;")

    def _get_track_data(self, track_id):
        """获取单集数据"""
        return self._api_request({"trackId": track_id})

    def _get_track_card(self, track_id):
        """获取单集音频卡片"""
        try:
            track_data = self._get_track_data(track_id)
            
            if not track_data or track_data.get("code") != 200:
                return self._create_text_reply("获取音频信息失败，请检查单集ID是否正确。")
            
            # 构建音乐卡片
            appmsg = self._construct_music_appmsg(
                track_data['title'],
                track_data['url'],
                track_data['cover'],
                track_data['nickname']
            )
            
            return self._create_app_reply(appmsg)
            
        except Exception as e:
            logger.error(f"[Ximalaya] Get track card error: {str(e)}")
            return self._create_text_reply("获取音频信息出错，请稍后重试。")

    def _get_album_data(self, album_id):
        """获取专辑数据"""
        return self._api_request({"albumId": album_id})

    def _get_episode_with_number(self, album_id, episode_number):
        """获取专辑中指定序号的音频，并返回音乐卡片"""
        try:
            # 获取专辑信息
            data = self._get_album_data(album_id)
            
            if not data or not data.get("data"):
                return self._create_text_reply("获取剧集列表失败，请检查专辑ID是否正确。")
            
            # 检查序号是否有效
            if episode_number < 1 or episode_number > len(data['data']):
                return self._create_text_reply(
                    f"序号无效。该专辑当前页面共{len(data['data'])}集，请输入1-{len(data['data'])}之间的数字。"
                )
            
            # 获取指定序号的音频信息
            episode = data['data'][episode_number - 1]
            track_data = self._get_track_data(episode['trackId'])
            
            if not track_data or track_data.get("code") != 200:
                return self._create_text_reply("获取音频信息失败，请稍后重试。")
            
            # 构建音乐卡片
            appmsg = self._construct_music_appmsg(
                track_data['title'],
                track_data['url'],
                track_data['cover'],
                track_data['nickname']
            )
            
            return self._create_app_reply(appmsg)
            
        except Exception as e:
            logger.error(f"[Ximalaya] Get episode with number error: {str(e)}")
            return self._create_text_reply("获取音频信息出错，请稍后重试。")

    def _search_audio(self, keyword, count=5):
        """搜索有声剧，返回指定数量的结果"""
        try:
            data = self._api_request({"name": keyword})
            
            if not data or not data.get("data"):
                return self._create_text_reply("未找到相关有声剧资源。")
            
            reply_content = f"🎧 为您找到以下有声剧：\n\n"
            
            # 限制显示结果数量
            results_count = min(count, len(data["data"]))
            
            # 显示指定数量的结果
            for idx, item in enumerate(data["data"][:results_count], 1):
                reply_content += f"{idx}. {item['title']}\n"
                reply_content += f"类型：{item['type']}\n"
                reply_content += f"专辑ID：{item['albumId']}\n"
                reply_content += f"作者：{item['Nickname']}\n"
                reply_content += f"封面：{item['cover']}\n"
                reply_content += "------------------------\n"
            
            reply_content += "\n💡 获取剧集列表，请发送：\n"
            reply_content += f"xm专辑 专辑ID [显示数量]\n"
            reply_content += "\n💡 直接点播音频，请发送：\n"
            reply_content += f"xm点播 专辑ID [序号]"
            
            return self._create_text_reply(reply_content)
        except Exception as e:
            logger.error(f"[Ximalaya] Search audio error: {str(e)}")
            return self._create_text_reply("搜索出错，请稍后重试。")

    def _get_album_info(self, album_id, count=10):
        """获取专辑信息并返回专辑列表"""
        try:
            data = self._get_album_data(album_id)
            
            if not data or not data.get("data"):
                return self._create_text_reply("获取剧集列表失败，请检查专辑ID是否正确。")
            
            # 检查专辑是否有剧集
            if not data['data'] or len(data['data']) == 0:
                return self._create_text_reply("该专辑暂无剧集。")
                
            # 构建专辑信息文本
            total_episodes = data['trackTotalCount']
            reply_content = f"📑 {data['albumTitle']}\n"
            reply_content += f"共{total_episodes}集\n\n"
            
            # 限制显示结果数量
            results_count = min(count, len(data['data']))
            
            # 显示专辑中的指定数量集数
            for idx, episode in enumerate(data['data'][:results_count], 1):
                reply_content += f"{idx}. {episode['title']}\n"
            
            reply_content += "\n💡 点播指定集数，请发送：\n"
            reply_content += f"xm点播 {album_id} 序号\n"
            
            if len(data['data']) < total_episodes:
                reply_content += f"\n💡 查看更多剧集，请发送：\n"
                reply_content += f"xm专辑 {album_id} {count+5}"
            
            return self._create_text_reply(reply_content)
                
        except Exception as e:
            logger.error(f"[Ximalaya] Get album info error: {str(e)}")
            return self._create_text_reply("获取专辑信息出错，请稍后重试。")

    def get_help_text(self, **kwargs):
        help_text = "🎧 喜马拉雅音频搜索插件使用说明\n"
        help_text += "🔍 指令格式：\n"
        help_text += "1. 搜索有声剧：\n"
        help_text += "   xm搜索 [剧名] [n]\n"
        help_text += "   - 剧名：要搜索的有声剧名称\n"
        help_text += "   - n：可选，显示结果数量，默认为5\n\n"
        help_text += "2. 获取剧集列表：\n"
        help_text += "   xm专辑 [专辑ID] [n]\n"
        help_text += "   - 专辑ID：喜马拉雅专辑ID\n"
        help_text += "   - n：可选，显示结果数量，默认为10\n\n"
        help_text += "3. 点播音频：\n"
        help_text += "   xm点播 [专辑ID] [序号]\n"
        help_text += "   - 专辑ID：喜马拉雅专辑ID\n"
        help_text += "   - 序号：可选，要点播的集数序号，默认为1\n\n"
        help_text += "💡 使用示例：\n"
        help_text += "1. 搜索剧集（返回前5条结果）：\n"
        help_text += "   xm搜索 三体\n\n"
        help_text += "2. 搜索剧集（返回前10条结果）：\n"
        help_text += "   xm搜索 三体 10\n\n"
        help_text += "3. 获取剧集列表（显示前10集）：\n"
        help_text += "   xm专辑 38378088\n\n"
        help_text += "4. 获取剧集列表（显示前20集）：\n"
        help_text += "   xm专辑 38378088 20\n\n"
        help_text += "5. 点播第一集：\n"
        help_text += "   xm点播 38378088\n\n"
        help_text += "6. 点播第3集：\n"
        help_text += "   xm点播 38378088 3\n"
        return help_text