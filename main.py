import sys
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GObject, Gio, GLib, Gdk, Graphene, Gsk
import vrchatapi
from vrchatapi.api import authentication_api, friends_api
from vrchatapi.exceptions import UnauthorizedException
from vrchatapi.models.two_factor_auth_code import TwoFactorAuthCode
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode
from vrchatapi.api import authentication_api, friends_api
from vrchatapi.exceptions import UnauthorizedException
from vrchatapi.models.two_factor_auth_code import TwoFactorAuthCode
from vrchatapi.models.two_factor_email_code import TwoFactorEmailCode
import os
import json
from http.cookiejar import LWPCookieJar
import hashlib
import base64
import requests
import pickle
import time
import threading
import websocket
import datetime
import copy


APP_TITLE = "Moonbeam VRC"
VERSION = "v0.1 indev"
USER_AGENT = 'taiko2k-moonbeam'
REQUEST_DL_HEADER = {
    'User-Agent': USER_AGENT,
}

DATA_FILE = 'user_data.pkl'
USER_ICON_CACHE = "cache/avatar1"


if not os.path.exists(USER_ICON_CACHE):
    os.makedirs(USER_ICON_CACHE)


def extract_filename(url):
    parts = url.split("/")
    for part in reversed(parts):
        if part.startswith("file_"):
            return part
    return None

COPY_FRIEND_PROPERTIES = [
    "location", "id", "last_platform", "display_name", "user_icon", "status", "status_description", "bio", "is_friend",
    "last_platform", "current_avatar_thumbnail_image_url", "note", "status_description", "tags", "profile_pic_override"
]

COPY_WORLD_PROPERTIES = [
    "author_id", "author_name", "capacity", "created_at", "description", "id", "thumbnail_image_url", "instances", "name",
    "recommended_capacity", "release_status", "instances"
]

language_emoji_dict = {
    "language_eng": "🇬🇧",  # English - UK Flag
    "language_kor": "🇰🇷",  # Korean
    "language_rus": "🇷🇺",  # Russian
    "language_spa": "🇪🇸",  # Spanish - Spain flag (but Spanish is spoken in many countries)
    "language_por": "🇵🇹",  # Portuguese - Portugal flag (also spoken widely in Brazil and other countries)
    "language_zho": "🇨🇳",  # Chinese - China flag (but also spoken in Taiwan and other places)
    "language_deu": "🇩🇪",  # German
    "language_jpn": "🇯🇵",  # Japanese
    "language_fra": "🇫🇷",  # French
    "language_swe": "🇸🇪",  # Swedish
    "language_nld": "🇳🇱",  # Dutch
    "language_pol": "🇵🇱",  # Polish
    "language_dan": "🇩🇰",  # Danish
    "language_nor": "🇳🇴",  # Norwegian
    "language_ita": "🇮🇹",  # Italian
    "language_tha": "🇹🇭",  # Thai
    "language_fin": "🇫🇮",  # Finnish
    "language_hun": "🇭🇺",  # Hungarian
    "language_ces": "🇨🇿",  # Czech
    "language_tur": "🇹🇷",  # Turkish
    "language_ara": "🇸🇦",  # Arabic - Saudi Arabia flag (but Arabic is spoken in many countries)
    "language_ron": "🇷🇴",  # Romanian
    "language_vie": "🇻🇳",  # Vietnamese
    "language_ase": "🇺🇸🤟",   # American Sign Language - Sign for 'I love you'
    "language_bfi": "🇬🇧🤟", # British Sign Language - Combining UK flag and the sign
    "language_dse": "🇳🇱🤟", # Dutch Sign Language - Combining Netherlands flag and the sign
    "language_fsl": "🇫🇷🤟", # French Sign Language - Combining French flag and the sign
    "language_kvk": "🇰🇷🤟"  # Korean Sign Language - Combining Korean flag and the sign
}


class Timer:
    def __init__(self, force=None):
        self.start = 0
        self.end = 0
        self.set()
        if force:
            self.force_set(force)

    def set(self):  # Reset
        self.start = time.monotonic()

    def hit(self):  # Return time and reset

        self.end = time.monotonic()
        elapsed = self.end - self.start
        self.start = time.monotonic()
        return elapsed

    def get(self):  # Return time only
        self.end = time.monotonic()
        return self.end - self.start

    def force_set(self, sec):
        self.start = time.monotonic()
        self.start -= sec


class RateLimiter:
    def __init__(self):
        self.last_call_time = None
        self.interval = 5
        self.burst = 5

    def inhibit(self):
        self.burst -= 1
        if self.burst <= 0:
            now = time.monotonic()
            if self.last_call_time is not None:
                elapsed = now - self.last_call_time
                if 0 <= elapsed < self.interval:
                    print(self.interval - elapsed)
                    print("COOLDOWN")
                    time.sleep(min(self.interval - elapsed, self.interval))

        self.last_call_time = time.monotonic()
        return

rl = RateLimiter()

RUNNING = True


def format_time(t):
    # Convert time (assuming it's in seconds since epoch) to a datetime object
    dt = datetime.datetime.fromtimestamp(t)
    current_dt = datetime.datetime.now()

    # Calculate the difference between the given time and current time
    time_diff = current_dt - dt

    if time_diff < datetime.timedelta(days=1):  # If the difference is less than 24 hours
        formatted_time = dt.strftime('%I:%M%p').lower()
    else:
        formatted_time = dt.strftime('%a %d %b %I:%M%p').replace(" 0", " ").lower()

    return formatted_time




class LogReader:
    def __init__(self, directory):
        self.directory = directory
        self.current_file = self._get_latest_log_file()
        self.last_position = self._set_initial_position()

    def _get_latest_log_file(self):
        """
        Returns the latest log file based on naming.
        """
        files = [f for f in os.listdir(self.directory) if f.startswith("output_log_")]
        files.sort(reverse=True)
        return files[0] if files else None

    def _set_initial_position(self):
        """
        Set the initial position to the end of the file.
        """
        if not self.current_file:
            return 0

        with open(os.path.join(self.directory, self.current_file), 'r') as f:
            f.seek(0, os.SEEK_END)
            return f.tell()

    def read_new_logs(self):
        """
        Check and return new log lines.
        Also, check for a newer log file.
        """
        new_logs = []

        # Check for a newer file
        latest_file = self._get_latest_log_file()
        if latest_file != self.current_file:
            self.current_file = latest_file
            self.last_position = 0

        if not self.current_file:
            return []

        with open(os.path.join(self.directory, self.current_file), 'rb') as f:
            #self.last_position = 0
            f.seek(self.last_position)
            content = f.read()
            if not content:
                return []
            logs = content.split(b"\n\n\r\n")

            # If the file's content ends with `\n\n\r\n`, then it indicates a complete log.
            if content.endswith(b"\n\n\r\n"):
                new_logs.extend(logs)
                self.last_position += len(content)
            else:
                # If there's more than one chunk, the last chunk might be incomplete. We'll read it next time.
                if len(logs) > 1:
                    new_logs.extend(logs[:-1])
                    self.last_position += len(b"\n\n\r\n".join(logs[:-1])) + len(logs[-1])
                else:
                    self.last_position += len(logs[0])

        return new_logs

class FriendRow(GObject.Object):
    name = GObject.Property(type=str, default='')
    location = GObject.Property(type=str, default='')
    public_count = GObject.Property(type=str, default='')
    status = GObject.Property(type=int, default=0)
    mini_icon_filepath = GObject.Property(type=str, default='')

    def __init__(self):
        super().__init__()
        self.name = ""
        self.location = ""
        self.mini_icon_filepath = None
        self.status = 0
        self.is_user = False
        self.id = None
        self.public_count = ""

class Friend():
    def __init__(self, **kwargs):
        for item in COPY_FRIEND_PROPERTIES:
            setattr(self, item, None)
        for key, value in kwargs.items():
            setattr(self, key, value)

    def get_banner_url(self):
        if hasattr(self, "profile_pic_override") and self.profile_pic_override:
            return self.profile_pic_override
        if hasattr(self, "current_avatar_thumbnail_image_url") and self.current_avatar_thumbnail_image_url:
            return self.current_avatar_thumbnail_image_url
        return ""

class World():
    def __init__(self, **kwargs):

        self.last_fetched = 1

        for item in COPY_WORLD_PROPERTIES:
            setattr(self, item, "")
        for key, value in kwargs.items():
            setattr(self, key, value)
    def load_from_api_model(self, w):
        for item in COPY_WORLD_PROPERTIES:
            setattr(self, item, getattr(w, item))

class Job:
    def __init__(self, name: str, data=None):
        self.name = name
        self.data = data

test = Job("a", "b")

class Event:
    def __init__(self, type="", content=None):
        self.timestamp = 0
        self.type = type
        self.subject = ""
        self.location = ""
        self.location_to = ""
        self.content = content

class Instance:
    def __init__(self):
        self.world_id = ""
        self.instance_id = ""  # e.g 12345
        self.instance_type = ""  # e.g private
        self.owner_id = ""
        self.can_request_invite = False
        self.region = ""  # e.g jp
        self.nonce = ""


class VRCZ:

    def __init__(self):
        self.logged_in = False

        self.current_user_name = ""  # in-game name
        self.friend_id_list = []
        self.friend_objects = {}
        self.user_object = None
        self.web_thread = None
        self.last_status = ""

        self.worlds = {}
        self.worlds_to_load = []

        self.error_log = []  # in event of any error, append human-readable string explaining error
        self.api_client = vrchatapi.ApiClient()
        self.api_client.user_agent = USER_AGENT
        self.auth_api = authentication_api.AuthenticationApi(self.api_client)
        self.world_api = vrchatapi.WorldsApi(self.api_client)
        self.cookie_file_path = 'cookie_data'

        self.log_file_timer = Timer()

        self.jobs = []
        self.posts = []

        self.events = []

        self.log_reader = None
        self.log_dir = os.path.expanduser("~/.local/share/Steam/steamapps/compatdata/438100/pfx/drive_c/users/steamuser/AppData/LocalLow/VRChat/VRChat")
        print(self.log_dir)
        if os.path.isdir(self.log_dir):
            print("VRCHAT Data folder found!")
            self.log_reader = LogReader(self.log_dir)
        else:
            print("VRCHAT Data folder NOT found")


    def update_from_log(self):
        if self.log_reader:
            got_urls = []
            for log in self.log_reader.read_new_logs():
                print(log)
                if b"[Video Playback] Attempting to resolve URL '" in log:
                    URL = log.split(b'\'')[-2].strip()
                    if URL in got_urls:
                        continue
                    print("Found video URL")
                    print(URL)
                    event = Event(type="video", content=(URL.decode("utf-8"), ""))
                    event.timestamp = time.time()
                    self.events.append(event)
                    job = Job(name="event", data=event)
                    self.posts.append(job)
                if b"[USharpVideo] Started video load for URL:" in log:
                    URL = log.split(b"URL:")[-1]
                    URL, RQ = URL.split(b",")
                    URL = URL.strip()
                    got_urls.append(URL)
                    RQ = RQ.split(b"by")[1]
                    RQ = RQ.strip()
                    print("Found video URL")
                    print((URL, RQ))
                    event = Event(type="video", content=(URL.decode("utf-8"), RQ.decode("utf-8")))
                    event.timestamp = time.time()
                    self.events.append(event)
                    job = Job(name="event", data=event)
                    self.posts.append(job)

    def process_event(self, event):
        #bm2
        event.timestamp = time.time()
        if event.type.startswith("friend-"):
            friend = self.friend_objects.get(event.content["userId"])
            if friend:
                event.subject = friend
                if event.type == "friend-online":
                    if friend:
                        friend.location = event.content["location"]
                if event.type == "friend-offline":
                    if friend:
                        friend.location = "offline"
                if event.type == "friend-location":
                    if friend:
                        friend.location = event.content["location"]

                self.events.append(event)
                job = Job(name="event", data=event)
                self.posts.append(job)
            else:
                print("Dunno about that friend :/")

    def on_error(self, ws, error):
        print("WebSocket Error:", error)

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket Closed. Status Code:", close_status_code, "Message:", close_msg)

    def on_message(self, ws, message):
        data = json.loads(message)

        type = data["type"]
        content = data["content"]
        if content and content.startswith("{"):
            content = json.loads(content)

        event = Event(type=type, content=content)
        job = Job("event", event)
        self.jobs.append(job)

    def web_monitor(self):
        print("Start websocket thread")
        def extract_auth_token_from_api_client(api_client):
            for cookie in api_client.rest_client.cookie_jar:
                if cookie.name == "auth":
                    return cookie.value
            return None

        auth_token = extract_auth_token_from_api_client(self.api_client)

        url = f"wss://pipeline.vrchat.cloud/?authToken={auth_token}"

        # Connect to the WebSocket with the error-handling callbacks
        ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            header=REQUEST_DL_HEADER
        )
        ws.run_forever()
        print("Leave websocket thread")

    def delete_cookies(self):
        if os.path.isfile(self.cookie_file_path):
            os.remove(self.cookie_file_path)

    def save_cookies(self):
        cookie_jar = LWPCookieJar(filename=self.cookie_file_path)
        for cookie in self.api_client.rest_client.cookie_jar:
            cookie_jar.set_cookie(cookie)
        cookie_jar.save()

    def load_cookies(self):
        if os.path.isfile(self.cookie_file_path):
            vrcz.logged_in = True
            cookie_jar = LWPCookieJar(self.cookie_file_path)
            try:
                cookie_jar.load()
            except FileNotFoundError:
                cookie_jar.save()
                return
            for cookie in cookie_jar:
                self.api_client.rest_client.cookie_jar.set_cookie(cookie)

    def load_app_data(self):  # Run on application start
        self.load_cookies()
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, 'rb') as file:
                d = pickle.load(file)
                # print(d)
                if "friends" in d:
                    for k, v in d["friends"].items():
                        friend = Friend(**v)
                        self.friend_objects[k] = friend
                if "self" in d:
                    self.user_object = Friend(**d["self"])
                if "events" in d:
                    self.events.extend(d["events"])
                    for e in self.events:
                        job = Job(name="event", data=e)
                        self.posts.append(job)
                if "worlds" in d:
                    for k, v in d["worlds"].items():
                        world = World(**v)
                        self.worlds[k] = world


    def save_app_data(self):
        if self.logged_in:
            self.save_cookies()
        d = {}
        friends = {}
        for k, v in self.friend_objects.items():
            friends[k] = v.__dict__

        worlds = {}
        for k, v in self.worlds.items():
            worlds[k] = copy.deepcopy(v.__dict__)
            del worlds[k]["instances"]
            del worlds[k]["last_fetched"]

        d["friends"] = friends
        d["self"] = self.user_object.__dict__
        d["events"] = self.events
        d["worlds"] = worlds
        with open(DATA_FILE, 'wb') as file:
            pickle.dump(d, file)

    def sign_in_step1(self, username, password):
        self.api_client.configuration.username = username
        self.api_client.configuration.password = password
        self.last_status = ""

        try:
            user = self.auth_api.get_current_user()
            self.logged_in = True
            self.current_user_name = user.display_name
        except UnauthorizedException as e:
            if "2 Factor Authentication" in e.reason:
                self.last_status = "2FA required. Please provide the code sent to your email."
                return
            else:
                print(f"Error during authentication: {e}")
                self.error_log.append(f"Error during authentication: {e}")
                self.last_status = "Authorization error. Check username and password."
                raise

    def sign_in_step2(self, email_code):
        try:
            self.auth_api.verify2_fa_email_code(two_factor_email_code=TwoFactorEmailCode(email_code))
            self.logged_in = True
            # Save authentication data for future use

        except Exception as e:
            self.error_log.append(f"Error during 2FA verification: {e}")
            raise ValueError(f"Error during 2FA verification: {e}")

    def update_local_friend_data(self, r):
        t = self.friend_objects.get(r.id)
        if not t:
            print("NEW FRIEND OBJECT")
            t = Friend()
        else:
            print("UPDATE FRIEND OBJECT")
            if t.display_name != r.display_name:
                print("Friend changed their name!")
                print(t)
                print(r)
        for key in COPY_FRIEND_PROPERTIES:
            if hasattr(r, key):
                setattr(t, key, getattr(r, key))
        job = Job("download-check-user-icon", t)
        self.jobs.append(job)
        job = Job("download-check-user-avatar-thumbnail", t)
        self.jobs.append(job)

        self.friend_objects[r.id] = t

    def update(self):

        # Try authenticate
        try:
            rl.inhibit()
            user = self.auth_api.get_current_user()
            self.logged_in = True
        except Exception as e:
            print("ERROR --1")
            print(str(e))
            self.logout()
            return 1

        self.current_user_name = user.display_name
        self.friend_id_list = user.friends

        print(user)
        fetch_offline = False

        for id in user.offline_friends:
            friend = self.friend_objects.get(id)
            if friend:
                friend.status = "offline"
                friend.location = "offline"
            else:
                fetch_offline = True
        for id in user.online_friends:
            friend = self.friend_objects.get(id)
            if friend:
                friend.status = "active"
                friend.location = "unknown"
        for id in user.active_friends:
            friend = self.friend_objects.get(id)
            if friend:
                friend.status = "active"
                friend.location = "offline"

        # Update user data
        if self.user_object is None:
            self.user_object = Friend()
        for key in COPY_FRIEND_PROPERTIES:
            try:
                setattr(self.user_object, key, getattr(user, key))
            except:
                print("no user key ", key)

        self.save_app_data()

        job = Job("download-check-user-icon", self.user_object)
        self.jobs.append(job)
        job = Job("download-check-user-avatar-thumbnail", self.user_object)
        self.jobs.append(job)

        job = Job("refresh-friend-db")
        self.jobs.append(job)

        if fetch_offline:
            print("Get offline friends as well")
            job = Job("refresh-friend-db-offline")
            self.jobs.append(job)

        print(f"Logged in as: {self.current_user_name}")

        job = Job("update-friend-list")
        vrcz.posts.append(job)


        if not self.web_thread or not self.web_thread.is_alive():
            self.web_thread = threading.Thread(target=self.web_monitor)
            self.web_thread.daemon = True
            self.web_thread.start()

        return 0

    def logout(self):
        print("Logout")
        self.logged_in = False
        self.delete_cookies()
        self.__init__()

    def worker(self):
        while RUNNING:
            if self.log_file_timer.get() > 10:
                self.log_file_timer.set()
                self.update_from_log()

            if self.worlds_to_load:
                id = self.worlds_to_load.pop()
                self.load_world(id)
                job = Job("update-friend-rows")
                self.posts.append(job)

            if self.jobs:
                job = self.jobs.pop(0)
                print("doing job")
                print(job.name)

                if job.name == "event":
                    self.process_event(job.data)

                if job.name == "refresh-friend-db-offline":

                    friends_api_instance = friends_api.FriendsApi(self.api_client)

                    n = 100
                    offset = 0
                    while True:
                        rl.inhibit()
                        next = friends_api_instance.get_friends(n=n, offset=offset, offline="true")
                        if not next:
                            break
                        for r in next:
                            #print(r)
                            self.update_local_friend_data(r)
                        job = Job("update-friend-list")
                        vrcz.posts.append(job)
                        offset += n
                        if len(next) < n:
                            break

                    self.save_app_data()
                    job = Job("update-friend-rows")
                    self.posts.append(job)
                    job = Job("update-friend-list")
                    self.posts.append(job)

                if job.name == "refresh-friend-db":
                    friends_api_instance = friends_api.FriendsApi(self.api_client)
                    n = 100
                    offset = 0
                    while True:
                        rl.inhibit()
                        next = friends_api_instance.get_friends(n=n, offset=offset)

                        if not next:
                            break
                        for r in next:
                            print(r)
                            self.update_local_friend_data(r)
                        job = Job("update-friend-list")
                        vrcz.posts.append(job)
                        offset += n
                        if len(next) < n:
                            break


                    self.save_app_data()
                    job = Job("update-friend-rows")
                    self.posts.append(job)
                    job = Job("update-friend-list")
                    self.posts.append(job)


                if job.name == "download-check-user-icon":

                    v = job.data
                    if v.user_icon and v.user_icon.startswith("http"):
                        print("check for icon")
                        key = extract_filename(v.user_icon)
                        if not key:
                            print("KEY ERROR")
                            print(key)
                            continue
                        key_path = os.path.join(USER_ICON_CACHE, key)
                        if key not in os.listdir(USER_ICON_CACHE):
                            print("download icon")

                            response = requests.get(v.user_icon, headers=REQUEST_DL_HEADER)
                            with open(key_path, 'wb') as f:
                                f.write(response.content)

                if job.name == "download-check-user-banner":
                    v = job.data
                    URL = v.get_banner_url()
                    if URL:
                        key = extract_filename(URL)
                        key_path = os.path.join(USER_ICON_CACHE, key)
                        if key not in os.listdir(USER_ICON_CACHE):
                            response = requests.get(URL, headers=REQUEST_DL_HEADER)
                            with open(key_path, 'wb') as f:
                                f.write(response.content)
                    job = Job("check-user-info-banner")
                    job.data = v
                    self.posts.append(job)


                if job.name == "download-check-user-avatar-thumbnail":

                    v = job.data
                    if v.current_avatar_thumbnail_image_url and v.current_avatar_thumbnail_image_url.startswith("http"):
                        print("check for icon")
                        key = extract_filename(v.current_avatar_thumbnail_image_url)
                        if not key:
                            print("KEY ERROR")
                            print(key)
                            continue
                        key_path = os.path.join(USER_ICON_CACHE, key)
                        if key not in os.listdir(USER_ICON_CACHE):
                            print("download icon")

                            response = requests.get(v.current_avatar_thumbnail_image_url, headers=REQUEST_DL_HEADER)
                            with open(key_path, 'wb') as f:
                                f.write(response.content)

            if not self.jobs:
                time.sleep(0.01)

    def parse_world_id(self, s):
        if not s:
            return None
        if not s.lower().startswith("wrld_"):
            return None
        return s.split(":")[0]

    def parse_world_instance(self, s):
        if not s:
            return None
        if not s.lower().startswith("wrld_"):
            return None
        if not ":" in s:
            return None
        line = s.split(":")[1].split("~")[0]
        if not line.isnumeric():
            print("parse error")
            return None
        return line

    def load_world(self, id, cached=True):
        print("load world1")
        if not id.lower().startswith("wrld_"):
            return None
        if cached and id in self.worlds:
            world = self.worlds[id]
            print(time.time() - world.last_fetched)
            if time.time() - world.last_fetched < 60 * 5:
                return world
        else:
            world = World()
        print("load world2")
        print(id)

        try:
            rl.inhibit()
            w = self.world_api.get_world(id)
            world.load_from_api_model(w)
            world.last_fetched = time.time()
        except Exception as e:
            print(str(e))

        #print(w)

        self.worlds[id] = world
        return world



vrcz = VRCZ()
vrcz.load_app_data()

thread = threading.Thread(target=vrcz.worker)
thread.daemon = True  # Set the thread as a daemon
thread.start()

class UserIconDisplay(Gtk.Widget):
    icon_path = GObject.Property(type=str, default='')
    status_mode = GObject.Property(type=int, default=0)
    def __init__(self):
        super().__init__()
        self.connect("notify::icon-path", self._on_icon_path_changed)
        self.connect("notify::status-mode", self._on_status_mode_changed)

        self.icon_texture = None

        self.rect = Graphene.Rect()
        self.point = Graphene.Point()
        self.colour = Gdk.RGBA()
        self.r_rect = Gsk.RoundedRect()

    def _on_status_mode_changed(self, widget, param):
        self.queue_draw()
    def _on_icon_path_changed(self, widget, param):
        #print(f"Icon path changed to: {self.icon_path}")
        if self.icon_path:
            if not os.path.isfile(self.icon_path):  # warning todo
                return
            self.icon_texture = Gdk.Texture.new_from_filename(self.icon_path)
            self.queue_draw()
        else:
            self.icon_texture = None
            self.queue_draw()

    def set_color(self, r, g, b, a=1.0):
        self.colour.red = r
        self.colour.green = g
        self.colour.blue = b
        self.colour.alpha = a

    def set_rect(self, x, y, w, h):
        self.rect.init(x, y, w, h)

    def set_r_rect(self, x, y, w, h, c=0):
        self.set_rect(x, y, w, h)
        self.r_rect.init_from_rect(self.rect, c)

    def do_snapshot(self, s):
        w = self.get_width()
        h = self.get_height()
        x = 0
        y = 0

        if self.icon_texture:
            self.set_r_rect(x, y, w, h, 360)
            s.push_rounded_clip(self.r_rect)
            s.append_texture(self.icon_texture, self.rect)
            s.pop()

        q = w * 0.37
        xx = w * 0.68
        yy = xx

        self.set_r_rect(xx, yy, q, q, 360)

        s.push_rounded_clip(self.r_rect)
        if self.status_mode == 0:
            self.set_color(0.2, 0.2, 0.2, 1)
        if self.status_mode == 1:
            self.set_color(0.7, 0.7, 0.7, 1)
        if self.status_mode == 2:
            self.set_color(0.35, 0.85, 0.3, 1)
        if self.status_mode == 3:
            self.set_color(0.8, 0.2, 0.2, 1)
        if self.status_mode == 4:
            self.set_color(0.3, 0.75, 1, 1)
        if self.status_mode == 5:
            self.set_color(0.8, 0.6, 0.2, 1)

        s.append_color(self.colour, self.rect)
        s.pop()

        self.set_color(0.1, 0.1, 0.1, 1)
        s.append_border(self.r_rect, [1] * 4, [self.colour] * 4)


        #s.append_color(self.colour, self.rect)



class UserInfoWindow(Adw.Window):
    def __init__(self):
        super().__init__()

        self.set_default_size(600, 400)


class MainWindow(Adw.ApplicationWindow):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.outer_box = Gtk.Box()

        self.set_default_size(1200, 650)
        self.set_title(APP_TITLE)

        self.nav = Adw.NavigationSplitView()
        self.nav.set_max_sidebar_width(240)
        self.set_content(self.nav)
        self.header = Adw.HeaderBar()
        self.n1 = Adw.NavigationPage()
        self.n0 = Adw.NavigationPage()
        self.t1 = Adw.ToolbarView()
        self.t1.add_top_bar(self.header)
        self.n1.set_child(self.t1)
        self.nav.set_content(self.n1)
        self.nav.set_sidebar(self.n0)

        self.vsw1 = Adw.ViewSwitcher()
        self.vst1 = Adw.ViewStack()
        self.vsw1.set_stack(self.vst1)

        self.header.set_title_widget(self.vsw1)
        self.t1.set_content(self.vst1)


        # ------------------ Info page

        self.info_box_clamp = Adw.Clamp()
        self.info_box_clamp.set_maximum_size(700)
        self.vst1.add_titled_with_icon(self.info_box_clamp, "info", "Player Info", "user-info-symbolic")

        self.info_box_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_style(self.info_box_holder, "view")

        self.info_box_outer_holder = Gtk.Box()
        self.info_box_clamp.set_child(self.info_box_outer_holder)
        self.info_box_outer_holder.append(self.info_box_holder)

        self.info_box_holder.set_margin_top(10)

        # self.info_box_footer = Gtk.Box()
        # self.info_box_footer.set_hexpand(True)
        # self.info_box_outer_holder.append(self.info_box_footer)

        # # Just empty space right now
        # self.info_box_header = Gtk.Box()
        # self.info_box_holder.append(self.info_box_header)
        # self.info_box_header.set_margin_top(10)

        self.row1and2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.row1and2.set_hexpand(True)

        self.row1and2andpic = Gtk.Box()
        self.row1and2andpic.append(self.row1and2)

        self.banner = Gtk.Image()
        self.banner.set_size_request(220, 150)

        # box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # box.append(self.banner)
        # box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # box2.set_vexpand(True)
        # box.append(box2)
        #
        # box3 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        # box2.set_hexpand(True)
        #
        # self.row1and2andpic.append(box3)
        self.row1and2andpic.append(self.banner)

        self.info_box_holder.append(self.row1and2andpic)

        self.row1 = Gtk.ListBox()
        self.row1and2.append(self.row1)
        self.row1.set_selection_mode(Gtk.SelectionMode.NONE)

        #self.info_box_holder.append(self.row1)
        self.row1and2.append(self.row1and2)

        self.info_name = Adw.ActionRow()
        self.info_name.set_subtitle("ExampleUser")
        self.info_name.set_subtitle_selectable(True)
        self.info_name.set_title("Display Name")
        self.set_style(self.info_name, "property")
        self.row1.append(self.info_name)

        self.row2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.row2.set_hexpand(True)
        self.row1and2.append(self.row2)
        self.status_row = Gtk.ListBox()
        self.status_row.set_selection_mode(Gtk.SelectionMode.NONE)
        self.row2.append(self.status_row)

        self.info_country = Adw.ActionRow()
        self.info_country.set_subtitle("🇬🇧")
        self.info_country.set_title("Language")
        self.set_style(self.info_country, "property")
        self.status_row.append(self.info_country)

        self.status_row = Gtk.ListBox()
        self.status_row.set_selection_mode(Gtk.SelectionMode.NONE)
        self.row2.append(self.status_row)

        self.info_platform = Adw.ActionRow()
        self.info_platform.set_subtitle("PC")
        self.info_platform.set_title("Platform")
        self.set_style(self.info_platform, "property")
        self.status_row.append(self.info_platform)

        self.status_row = Gtk.ListBox()
        self.status_row.set_selection_mode(Gtk.SelectionMode.NONE)
        self.row2.append(self.status_row)

        self.info_rank = Adw.ActionRow()
        self.info_rank.set_subtitle("Trusted User")
        self.info_rank.set_title("Rank")
        self.set_style(self.info_rank, "property")
        self.status_row.append(self.info_rank)


        #self.info_box_holder.append(self.row2)

        # ----------------------------------------------------


        style_context = self.get_style_context()
        style_context.add_class('devel')

        #self.set_titlebar()

        # Friend list box
        self.friend_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        #self.friend_list_box.set_size_request(150, -1)
        #self.outer_box.append(self.friend_list_box)

        self.n0.set_child(self.friend_list_box)

        self.friend_data = {}
        self.friend_list_view = Gtk.ListView()
        self.friend_list_scroll = Gtk.ScrolledWindow()
        self.friend_list_scroll.set_vexpand(True)
        self.friend_list_scroll.set_child(self.friend_list_view)
        self.friend_list_box.append(self.friend_list_scroll)
        self.friend_ls = Gio.ListStore(item_type=FriendRow)
        self.friend_ls_dict = {}

        self.ss = Gtk.SingleSelection()
        self.ss.set_model(self.friend_ls)
        self.friend_list_view.set_model(self.ss)

        factory = Gtk.SignalListItemFactory()

        self.ss.connect("selection-changed", self.on_selected_friend_changed)
        self.friend_list_view.connect("activate", self.on_selected_friend_click)
        def f_setup(fact, item):

            holder = Gtk.Box()
            holder.set_margin_top(5)
            holder.set_margin_bottom(5)
            holder.set_margin_start(6)

            icon = UserIconDisplay()
            icon.set_size_request(35, 35)
            holder.append(icon)

            # image = Gtk.Image()
            # image.set_size_request(40, 40)
            # holder.append(image)

            label = Gtk.Label(halign=Gtk.Align.START)
            label.set_selectable(False)
            label.set_margin_start(10)
            label.set_use_markup(True)

            text_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

            holder.append(text_vbox)
            text_vbox.append(label)

            item.set_child(holder)
            item.label = label
            item.icon = icon

            status_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)


            label = Gtk.Label(halign=Gtk.Align.START)
            label.set_selectable(False)
            label.set_margin_start(10)
            label.set_use_markup(True)
            label.set_markup("")
            item.location_label = label

            status_hbox.append(label)

            label = Gtk.Label(halign=Gtk.Align.START)
            label.set_selectable(False)
            label.set_margin_start(5)
            label.set_use_markup(True)
            label.set_markup("")
            item.public_count = label
            status_hbox.append(label)


            text_vbox.append(status_hbox)




        factory.connect("setup", f_setup)

        def f_bind(fact, row):
            friend = row.get_item()

            friend.bind_property("name",
                          row.label, "label",
                          GObject.BindingFlags.SYNC_CREATE)

            friend.bind_property("location",
                          row.location_label, "label",
                          GObject.BindingFlags.SYNC_CREATE)

            friend.bind_property("public_count",
                          row.public_count, "label",
                          GObject.BindingFlags.SYNC_CREATE)

            friend.bind_property("mini_icon_filepath",
                          row.icon, "icon_path",
                          GObject.BindingFlags.SYNC_CREATE)

            friend.bind_property("status",
                          row.icon, "status_mode",
                          GObject.BindingFlags.SYNC_CREATE)

        factory.connect("bind", f_bind)

        self.friend_list_view.set_factory(factory)

        # ---------------

        self.event_box_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.c4 = Adw.Clamp()
        self.c4.set_maximum_size(1000)
        self.c4.set_child(self.event_box_holder)
        self.vst1.add_titled_with_icon(self.c4, "event", "Event Log", "find-location-symbolic")

        self.events_empty = True
        self.events_empty_status = Adw.StatusPage()
        self.events_empty_status.set_title("No events yet")
        self.events_empty_status.set_icon_name("help-about-symbolic")
        self.events_empty_status.set_vexpand(True)
        self.event_box_holder.append(self.events_empty_status)

        self.event_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.event_box.set_margin_top(5)

        self.event_scroll = Gtk.ScrolledWindow()
        self.event_scroll.set_vexpand(True)
        self.event_scroll.set_child(self.event_box)




        # ----------------
        self.outer_box.append(Gtk.Separator())

        self.dev_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.dev_box.set_margin_top(12)
        self.c2 = Adw.Clamp()
        self.c2.set_child(self.dev_box)
        self.vst1.add_titled_with_icon(self.c2, "dev", "Dev Menu", "pan-down-symbolic")
        self.dev_label = Gtk.Label(label="Dev Menu")
        #self.notebook.append_page(self.dev_box, self.dev_label)

        self.test_button = Gtk.Button(label="Connect and Update")
        self.test_button.connect("clicked", self.test3)
        self.dev_box.append(self.test_button)

        # self.test_button = Gtk.Button(label="Load Friend List")
        # self.test_button.connect("clicked", self.test2)
        # self.dev_box.append(self.test_button)

        # self.gps_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # self.gps_label = Gtk.Label(label="GPS")
        # self.notebook.append_page(self.gps_box, self.gps_label)
        #
        # self.user_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # self.user_info_label = Gtk.Label(label="User Info")
        # self.notebook.append_page(self.user_info_box, self.user_info_label)

        #self.outer_box.append(Gtk.Separator())

        # Login box
        self.login_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.c3 = Adw.Clamp()
        self.c3.set_child(self.login_box)
        self.vst1.add_titled_with_icon(self.c3, "login", "Login", "dialog-password-symbolic")

        #self.login_box.set_size_request(200, -1)
        self.login_box.set_spacing(6)
        self.login_box.set_margin_top(12)
        self.login_box.set_margin_bottom(12)
        self.login_box.set_margin_start(12)
        self.login_box.set_margin_end(12)
        #self.outer_box.append(self.login_box)

        self.stage1_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)


        self.username_entry = Gtk.Entry(placeholder_text="Username")
        self.username_entry.set_margin_bottom(5)
        self.password_entry = Gtk.Entry(placeholder_text="Password", visibility=False)
        self.password_entry.set_margin_bottom(10)

        self.stage1_box.append(self.username_entry)
        self.stage1_box.append(self.password_entry)


        self.request_code_button = Gtk.Button(label="Request Code")
        self.request_code_button.set_margin_bottom(30)
        self.request_code_button.connect("clicked", self.activate_get_code)
        self.stage1_box.append(self.request_code_button)

        self.login_status_label = Gtk.Label(label="")
        self.stage1_box.append(self.login_status_label)


        self.login_box.append(self.stage1_box)

        self.stage2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stage2_box.set_visible(False)



        self.two_fa_entry = Gtk.Entry(placeholder_text="2FA Code")
        self.two_fa_entry.set_margin_bottom(10)

        self.stage2_box.append(self.two_fa_entry)

        self.login_button = Gtk.Button(label="Verify Code")
        self.login_button.connect("clicked", self.activate_verify_code)
        self.stage2_box.append(self.login_button)
        self.login_button.set_margin_bottom(60)
        self.login_box.append(self.stage2_box)

        self.stage3_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stage3_box.set_visible(False)

        self.logout_button = Gtk.Button(label="Logout")
        self.logout_button.connect("clicked", self.activate_logout)
        self.logout_button.set_margin_bottom(20)
        self.stage3_box.append(self.logout_button)
        self.login_box.append(self.stage3_box)

        if os.path.isfile(vrcz.cookie_file_path):
            self.stage1_box.set_visible(False)
            self.stage3_box.set_visible(True)


        # self.test_button = Gtk.Button(label="_test")
        # self.test_button.connect("clicked", self.activate_test)
        # self.login_box.append(self.test_button)

        #self.login_box.set_visible(False)

        self.update_friend_list()


        # self.user_window = UserInfoWindow()
        # self.user_window.set_transient_for(self)
        # self.user_window.set_modal(True)
        # self.user_window.set_destroy_with_parent(True)
        # self.user_window.show()
        self.hand_cursor = Gdk.Cursor.new_from_name("pointer")
        self.css_provider = Gtk.CssProvider()
        self.css_provider.load_from_string('''
            button {
                background: none;
                border: none;
                padding: 0;
                outline: none;
            }
            button:hover {
                border: none;
                outline: none;
            }

        ''')

        self.selected_user_info = None

        GLib.timeout_add(900, self.heartbeat)


    def set_button_as_label(self, button):  # remove me
        style_context = button.get_style_context()
        style_context.add_provider(self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def set_style(self, target, name):
        style_context = target.get_style_context()
        style_context.add_class(name)

    def set_profie_view(self, id):

        print("Set profile view")
        if id == vrcz.user_object.id:
            p = vrcz.user_object
        elif id in vrcz.friend_objects:
            p = vrcz.friend_objects[id]
        else:
            print("Need to get user data")
            return

        self.selected_user_info = p

        URL = p.get_banner_url()
        if URL:
            # print("URL")
            # print(URL)
            key = extract_filename(URL)
            key_path = os.path.join(USER_ICON_CACHE, key)
            if os.path.isfile(key_path):
                self.banner.set_from_file(key_path)
            else:
                self.banner.set_from_icon_name("image-loading-symbolic")
                job = Job("download-check-user-banner")
                job.data = p
                vrcz.jobs.append(job)
        else:
            self.banner.set_from_file(None)

        self.info_name.set_subtitle(p.display_name)
        lang_line = " "
        if p.tags:
            for tag in p.tags:
                if tag in language_emoji_dict:
                    flag = language_emoji_dict.get(tag)
                    lang_line += flag + "  "
        self.info_country.set_subtitle(lang_line)

        platform = ""
        if p.last_platform == "standalonewindows":
            platform = "PC"
        elif p.last_platform == "android":
            platform = "Android/Quest"
        elif p.last_platform:
            platform = p.last_platform
        self.info_platform.set_subtitle(platform)

        rank = "Visitor"
        if p.tags:
            if "system_trust_basic" in p.tags:
                rank = "New User"
            if "system_trust_known" in p.tags:
                rank = "User"
            if "system_trust_trusted" in p.tags:
                rank = "Known User"
            if "system_trust_veteran" in p.tags:
                rank = "Trusted User"
        else:
            rank = "Unknown"
        self.info_rank.set_subtitle(rank)

        # world_id = vrcz.parse_world_id(p.location)
        # vrcz.load_world(world_id)


    def on_selected_friend_click(self, view, n):
        selected_item = self.ss.get_selected_item()
        if selected_item is not None:
            self.set_profie_view(selected_item.id)
        self.vst1.set_visible_child_name("info")
    def on_selected_friend_changed(self, selection, position, n_items):
        selected_item = selection.get_selected_item()
        if selected_item is not None:
            self.set_profie_view(selected_item.id)

    def set_friend_row_data(self, id):

        row = self.friend_data.get(id)
        friend = vrcz.friend_objects.get(id)
        if friend is None and id == vrcz.user_object.id:
            friend = vrcz.user_object
        if row and friend:

            row.name = f"<b>{friend.display_name}</b>"

            if not friend.location:
                row.location = "<small>Unknown</small>"
            elif friend.location == "offline":
                row.location = f"<span foreground=\"#aaaaaa\"><b><small>Offline</small></b></span>"
            elif friend.location == "private":
                row.location = f"<span foreground=\"#de7978\"><b><small>Private</small></b></span>"
            else:
                row.location = f"<span foreground=\"#aaaaaa\"><b><small>{friend.location.capitalize()}</small></b></span>"

            count = ""
            world_id = vrcz.parse_world_id(friend.location)
            if world_id:
                if world_id in vrcz.worlds:
                    world = vrcz.worlds[world_id]

                    #row.location = f"<small>{world.name}</small>"
                    row.location = f"<span foreground=\"#efb5f5\"><b><small>{world.name}</small></b></span>"

                    if "~hidden" not in friend.location:
                        if world.last_fetched and time.time() - world.last_fetched > 60 * 5:
                            print("request world reload")
                            vrcz.worlds_to_load.append(world_id)

                        print("OK")
                        print(world.name)
                        print(friend.location)
                        print(world.instances)

                        if world.instances:
                            player_instance = vrcz.parse_world_instance(friend.location)
                            if player_instance:
                                for instance in world.instances:
                                    if instance[0].split("~")[0] == player_instance:
                                        count = f"<span foreground=\"#f2d37e\"><b><small>{str(instance[1])}</small></b></span>"
                                        break
                                else:
                                    print("no match")
                            else:
                                print("no parse")
                        else:
                            print("no instances")

                else:
                    if world_id not in vrcz.worlds_to_load:
                        vrcz.worlds_to_load.append(world_id)

            if row.public_count != count:
                row.public_count = count

            new = 0
            if friend.status == "offline":
                new = 0
            elif friend.status != "offline" and friend.location == "offline":
                new = 1
            elif friend.status == "active" and friend.location != "offline":
                new = 2
            elif friend.status == "busy" and friend.location != "offline":
                new = 3
            elif friend.status == "join me" and friend.location != "offline":
                new = 4
            elif friend.status == "ask me" and friend.location != "offline":
                new = 5

            row.status = new


            if friend.user_icon:
                key = extract_filename(friend.user_icon)
                if key:
                    key_path = os.path.join(USER_ICON_CACHE, key)
                    if row.mini_icon_filepath != key_path:
                        row.mini_icon_filepath = key_path
            elif friend.current_avatar_thumbnail_image_url:
                key = extract_filename(friend.current_avatar_thumbnail_image_url)
                if key:
                    key_path = os.path.join(USER_ICON_CACHE, key)
                    if row.mini_icon_filepath != key_path:
                        row.mini_icon_filepath = key_path

    def click_user(self, button, user):
        print(user)

    def heartbeat(self):
        update_friend_list = False
        update_friend_rows = False
        while vrcz.posts:
            post = vrcz.posts.pop(0)
            #print("post")
            print(post.name)

            if post.name == "check-user-info-banner":
                if self.selected_user_info and self.selected_user_info == post.data:
                    URL = self.selected_user_info.get_banner_url()
                    key = extract_filename(URL)
                    key_path = os.path.join(USER_ICON_CACHE, key)
                    if URL and os.path.isfile(key_path):
                        self.banner.set_from_file(key_path)
                    else:
                        self.banner.set_from_file(None)
            if post.name == "update-friend-list":
                update_friend_list = True
            if post.name == "update-friend-rows":
                update_friend_rows = True
            if post.name == "event":
                # bm1
                event = post.data

                if event.type == "friend-active":
                    continue
                if event.type == "friend-update":
                    continue

                box = Gtk.Box()
                box.set_margin_bottom(0)
                print(event.type)


                label = Gtk.Label(label=format_time(event.timestamp))
                self.set_style(label, "dim-label")
                self.set_style(label, "monospace")
                label.set_margin_end(3)
                label.set_size_request(70, -1)
                label.set_xalign(0)
                box.append(label)


                if event.type == "video":
                    URL, RQ = event.content
                    label = Gtk.Label()
                    label.set_markup(f"Video play")
                    box.append(label)

                    print(URL)
                    lb = Gtk.LinkButton.new(URL)
                    lb.set_margin_end(5)
                    lb.set_margin_start(5)
                    self.set_button_as_label(lb)

                    box.append(lb)

                    if RQ:
                        label = Gtk.Label()
                        label.set_markup(f"by {RQ}")
                        label.set_margin_end(5)
                        box.append(label)

                    self.event_box.prepend(box)


                if event.type.startswith("friend-"):
                    if self.events_empty:
                        self.events_empty = False
                        self.event_box_holder.remove(self.events_empty_status)
                        self.event_box_holder.append(self.event_scroll)

                    user = event.subject
                    if user:
                        label = Gtk.Label()
                        if user.location != "offline" or True:
                            label.set_markup(f"<span foreground=\"#16f2ca\" weight=\"bold\">{user.display_name}</span>")
                        # else:
                        #     label.set_markup(f"<span weight=\"bold\">{user.display_name}</span>")
                        #     self.set_style(label, "dim-label")

                        b = Gtk.Button()
                        b.connect("clicked", self.click_user, user)
                        b.set_cursor(self.hand_cursor)
                        b.set_child(label)

                        self.set_button_as_label(b)

                        b.set_margin_end(5)
                        box.append(b)

                        if event.type == "friend-online":
                            label = Gtk.Label()
                            label.set_markup(f"came <b>online</b>")
                            label.set_margin_end(5)
                            box.append(label)

                        if event.type == "friend-offline":
                            label = Gtk.Label()
                            label.set_markup(f"went <b>offline</b>")
                            label.set_margin_end(5)
                            box.append(label)

                        if event.type == "friend-location":
                            if event.content["location"] == "traveling":
                                target = event.content["travelingToLocation"]
                                # /if target == "private" or not target:
                                label = Gtk.Label()
                                label.set_markup(f"is on the move")
                                label.set_margin_end(5)
                                box.append(label)
                                # else:
                                #     label = Gtk.Label()
                                #     label.set_markup(f"is traveling to")
                                #     label.set_margin_end(5)
                                #     box.append(label)
                                #
                                #     label = Gtk.Label()
                                #     label.set_markup(f"{target[:25]}...")
                                #     label.set_margin_end(5)
                                #     box.append(label)
                            else:
                                #target = user.location
                                target = event.content["travelingToLocation"]
                                if not target:
                                    target = event.content["location"]
                                print("aa")
                                print(event.content)
                                print(target)
                                if target == "private" or not target:
                                    label = Gtk.Label()
                                    label.set_markup(f" > Hidden location")
                                    label.set_margin_end(5)
                                    box.append(label)
                                else:
                                    label = Gtk.Label()
                                    label.set_markup(f" > ")
                                    label.set_margin_end(5)
                                    box.append(label)

                                    text = target
                                    world_id = vrcz.parse_world_id(target)
                                    if world_id:
                                        if world_id in vrcz.worlds:
                                            world = vrcz.worlds[world_id]
                                            text = world.name
                                        else:
                                            if world_id not in vrcz.worlds_to_load:
                                                vrcz.worlds_to_load.append(world_id)


                                    label = Gtk.Label()
                                    label.set_markup(f"{text}")
                                    label.set_markup(
                                        f"<span foreground=\"#ec90f5\" weight=\"bold\">{text}</span>")
                                    label.set_margin_end(5)
                                    box.append(label)


                    self.event_box.prepend(box)
                    job = Job("update-friend-list")
                    vrcz.posts.append(job)

        if update_friend_rows:
            print("UPDATE ROWS")
            for k, v in self.friend_data.items():
                self.set_friend_row_data(k)
        if update_friend_list:
            print("UPDATE LIST")
            self.update_friend_list()

        GLib.timeout_add(1000, self.heartbeat)

    def test2(self, button):
        #self.update_friend_list()
        job = Job("update-friend-list")

        # for k, v in self.friend_data.items():
        #     self.set_friend_row_data(k)

        vrcz.posts.append(job)

    def test3(self, button):
        button.set_sensitive(False)
        if vrcz.update():
            self.login_box.set_visible(True)


    def update_friend_list(self):

        if vrcz.user_object and vrcz.user_object.id not in self.friend_data:
            fd = FriendRow()
            fd.is_user = True
            fd.id = vrcz.user_object.id
            self.friend_data[vrcz.user_object.id] = fd
            self.set_friend_row_data(vrcz.user_object.id)
            self.friend_ls.append(fd)

        for k, v in vrcz.friend_objects.items():
            if k not in self.friend_data:
                fd = FriendRow()
                fd.id = k
                self.friend_data[k] = fd
                self.set_friend_row_data(k)
                self.friend_ls.append(fd)

        def get_weight(row):
            if row.is_user:
                return -1
            if row.status == 4:
                return 0
            if row.status == 2:
                return 1
            if row.status == 5:
                return 2
            if row.status == 3:
                return 3
            if row.status == 1:
                return 4
            return 5


        def compare(a, b):

            aw = get_weight(a)
            bw = get_weight(b)
            if aw == bw:
                return 0
            if aw < bw:
                return -1
            return 1

        self.friend_ls.sort(compare)


    def activate_test(self, button):
        vrcz.update()

    def activate_get_code(self, button):
        username = self.username_entry.get_text()
        password = self.password_entry.get_text()
        self.login_status_label.set_text("")

        try:
            vrcz.sign_in_step1(username, password)
            self.login_status_label.set_text(vrcz.last_status)
            self.stage3_box.set_visible(False)
            self.stage2_box.set_visible(True)
            self.stage1_box.set_visible(False)
        except Exception as e:
            print(e)
            self.login_status_label.set_text(vrcz.last_status)

    def activate_verify_code(self, button):
        self.login_status_label.set_text("")
        code = self.two_fa_entry.get_text()
        try:
            vrcz.sign_in_step2(code)
            if vrcz.update():
                self.stage3_box.set_visible(True)
                self.stage2_box.set_visible(False)
                self.stage1_box.set_visible(False)
            else:
                self.stage3_box.set_visible(False)
                self.stage2_box.set_visible(False)
                self.stage1_box.set_visible(True)
        except ValueError as e:
            print(e)

    def activate_logout(self, button):
        self.stage3_box.set_visible(False)
        self.stage2_box.set_visible(False)
        self.stage1_box.set_visible(True)
        vrcz.logout()
        # Here you can also reset the UI fields if needed


class MOONBEAM(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.win = None
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self.win = MainWindow(application=app)
        self.win.present()


app = MOONBEAM(application_id="com.github.taiko2k.moonbeam")
app.run(sys.argv)

vrcz.user_object.location = "offline"
vrcz.user_object.status = "offline"
for k, v in vrcz.friend_objects.items():
    v.location = "offline"
    v.status = "offline"
vrcz.save_app_data()
RUNNING = False
time.sleep(1)