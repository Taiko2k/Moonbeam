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
import traceback
from unidecode import unidecode


APP_TITLE = "Moonbeam"
VERSION = "v0.1 indev"
APP_ID = "com.github.taiko2k.moonbeam"
USER_AGENT = 'moonbeam/indev captain.gxj@gmail.com'
REQUEST_DL_HEADER = {
    'User-Agent': USER_AGENT,
}

DATA_FILE = 'user_data.pkl'
USER_ICON_CACHE = "cache/avatar1"
WORLD_ICON_CACHE = "cache/world1"

WORLD_CACHE_DURATION = 60 * 5
INSTANCE_CACHE_DURATION = 60 * 3

if not os.path.exists(USER_ICON_CACHE):
    os.makedirs(USER_ICON_CACHE)

if not os.path.exists(WORLD_ICON_CACHE):
    os.makedirs(WORLD_ICON_CACHE)


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

COPY_INSTANCE_PROPERTIES = {
    "active", "can_request_invite", "capacity", "instance_id", "location", "name", "n_users", "region", "platforms",
    "world_id"
}

def location_to_instance_type(location):
    instance_type = ""
    if "~groupAccessType(public)" in location:
        instance_type = "Public"
    elif "public" in location:
        instance_type = "Public"
    elif "hidden" in location:
        instance_type = "Friends+"
    elif "friends" in location:
        instance_type = "Friends"
    elif ":" in location:
        instance_type = "Public"
    return instance_type

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

failed_files = []

class Timer:
    def __init__(self, force=None):
        self.start = 0
        self.end = 0
        self.set()
        if force:
            self.force_set(force)

    def set(self):  # Reset
        self.start = time.time()

    def hit(self):  # Return time and reset

        self.end = time.time()
        elapsed = self.end - self.start
        self.start = time.time()
        return elapsed

    def get(self):  # Return time only
        self.end = time.time()
        return self.end - self.start

    def force_set(self, sec):
        self.start = time.time()
        self.start -= sec


class RateLimiter:
    def __init__(self):
        self.last_call_time = None
        self.interval = 5
        self.burst = 3

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
        formatted_time = dt.strftime('%d %b %I:%M%p').replace(" 0", " ").lower()

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
        self.is_favorite = False
        self.public_count = ""

class Friend():
    def __init__(self, **kwargs):
        for item in COPY_FRIEND_PROPERTIES:
            setattr(self, item, "")
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

        self.last_fetched = None

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
    def __init__(self, instance):

        self.last_fetched = Timer()
        for item in COPY_INSTANCE_PROPERTIES:
            setattr(self, item, "")
        for item in COPY_INSTANCE_PROPERTIES:
            setattr(self, item, getattr(instance, item))



class VRCZ:

    def __init__(self):
        self.logged_in = False
        self.initial_update = False

        self.current_user_name = ""  # in-game name
        self.friend_id_list = []
        self.friend_objects = {}

        self.instance_cache = {}
        self.instances_to_load = []

        self.user_object = None
        self.web_thread = None
        self.last_status = ""

        self.worlds = {}
        self.worlds_to_load = []

        self.error_log = []  # in event of any error, append human-readable string explaining error
        self.api_client = vrchatapi.ApiClient()
        self.api_client.user_agent = USER_AGENT
        self.api_client.configuration.safe_chars_for_path_param += "~()"
        self.auth_api = authentication_api.AuthenticationApi(self.api_client)
        self.world_api = vrchatapi.WorldsApi(self.api_client)
        self.instance_api = vrchatapi.InstancesApi(self.api_client)
        self.favorites_api = vrchatapi.FavoritesApi(self.api_client)

        self.favorite_friends = {}

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

        self.online_friend_db_update_timer = None
        self.offline_friend_db_update_timer = None
        self.ws = None


    # def instance_from_location(self, location):
    #     if not location or not location.lower().startswith("wrld_") or not ":" in location:
    #         return None
    #
    #     if location in self.instance_cache:
    #         i = self.instance_cache[location]
    #         if i is None:
    #             return None
    #         if i.last_fetched and i.last_fetched.get() < INSTANCE_CACHE_DURATION:
    #             return i
    #         else:
    #             print("instance expired")
    #
    #     if location in self.instances_to_load:
    #         return None
    #     print("request load instance")
    #     self.instances_to_load.append(location)
    #
    #     return None

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
        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            header=REQUEST_DL_HEADER
        )
        self.ws.run_forever()
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
                if "db_online_time" in d:
                    self.online_friend_db_update_timer = Timer()
                    self.online_friend_db_update_timer.start = d["db_online_time"]
                if "db_offline_time" in d:
                    self.offline_friend_db_update_timer = Timer()
                    self.offline_friend_db_update_timer.start = d["db_offline_time"]

    def save_app_data(self):
        if not self.logged_in:
            return
        self.save_cookies()

        d = {}
        friends = {}
        for k, v in self.friend_objects.items():
            friends[k] = v.__dict__

        worlds = {}
        for k, v in self.worlds.items():
            worlds[k] = copy.deepcopy(v.__dict__)
            del worlds[k]["instances"]
            #del worlds[k]["last_fetched"]

        d["friends"] = friends
        d["self"] = self.user_object.__dict__
        d["events"] = self.events
        d["worlds"] = worlds
        if self.online_friend_db_update_timer:
            d["db_online_time"] = self.online_friend_db_update_timer.start
        if self.offline_friend_db_update_timer:
            d["db_offline_time"] = self.offline_friend_db_update_timer.start
        with open(DATA_FILE, 'wb') as file:
            pickle.dump(d, file)

    def sign_in_step1(self, username, password):
        try:
            self.auth_api.logout()
        except:
            pass
        self.api_client.configuration.username = username
        self.api_client.configuration.password = password
        self.last_status = ""


        user = self.auth_api.get_current_user()
        self.logged_in = True
        self.current_user_name = user.display_name


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

        if t not in failed_files:
            job = Job("download-check-user-icon", t)
            self.jobs.append(job)
            job = Job("download-check-user-avatar-thumbnail", t)
            self.jobs.append(job)

        self.friend_objects[r.id] = t

    def update(self):
        if "-n" in sys.argv:
            print("skip update")
            job = Job("login-done")
            self.posts.append(job)
            return

        # Try authenticate
        try:
            rl.inhibit()
            user = self.auth_api.get_current_user()
            self.logged_in = True

        except Exception as e:
            print("ERROR --1")
            print(str(e))
            job = Job("login-reset")
            self.posts.append(job)
            return 1

        job = Job("login-done")
        self.posts.append(job)

        self.current_user_name = user.display_name
        self.friend_id_list = user.friends

        print(user)

        for id in user.offline_friends:
            friend = self.friend_objects.get(id)
            if friend:
                friend.status = "offline"
                friend.location = "offline"
        for id in user.online_friends:
            friend = self.friend_objects.get(id)
            if friend:
                friend.status = "active"

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

        go = False
        if not self.online_friend_db_update_timer:
            self.online_friend_db_update_timer = Timer()
            go = True
        elif self.online_friend_db_update_timer.get() > 30:  # 30s
            go = True
        print(self.online_friend_db_update_timer.get())
        if go:
            job = Job("refresh-friend-db")
            self.jobs.append(job)
        else:
            print("App was quickly restarted, skipping online update")
        self.online_friend_db_update_timer.set()

        go = False
        if not self.offline_friend_db_update_timer:
            self.offline_friend_db_update_timer = Timer()
            go = True
        else:
            if self.offline_friend_db_update_timer.get() > 60 * 60 * 3:  # 3h
                go = True

        if go:
            print("Get offline friends as well")
            job = Job("refresh-friend-db-offline")
            self.jobs.append(job)
            self.offline_friend_db_update_timer.set()
        else:
            print("Skip update offline friends")

        if self.user_object not in failed_files:
            job = Job("download-check-user-icon", self.user_object)
            self.jobs.append(job)
            job = Job("download-check-user-avatar-thumbnail", self.user_object)
            self.jobs.append(job)

        ff = self.favorites_api.get_favorites(n=100, offset=0, type="friend")
        self.favorite_friends.clear()
        if ff:
            for fav in ff:
                self.favorite_friends[fav.favorite_id] = fav.id


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
        if self.logged_in:
            try:
                self.auth_api.logout()
            except:
                pass
        self.logged_in = False
        self.delete_cookies()

    def worker(self):
        while RUNNING:

            if self.logged_in and not self.initial_update:
                print("INITIAL UPDATE")
                self.initial_update = True
                self.update()

            if self.log_file_timer.get() > 10:
                self.log_file_timer.set()
                self.update_from_log()

            if self.worlds_to_load:
                id = self.worlds_to_load[0]
                self.load_world(id)
                del self.worlds_to_load[0]
                job = Job("update-friend-rows")
                self.posts.append(job)

            if self.instances_to_load:
                print("Job load instance")
                location = self.instances_to_load[0]
                print(location)

                self.load_location(location)
                del self.instances_to_load[0]
                job = Job("update-friend-rows")
                self.posts.append(job)
                job = Job("update-instance-info", location)
                self.posts.append(job)



            if self.jobs:
                job = self.jobs.pop(0)
                print("Doing Job...")
                print(job.name)

                if job.name == "login":
                    username, password, code = job.data
                    try:
                        if code:
                            self.sign_in_step2(code)
                        else:
                            self.sign_in_step1(username, password)
                        job = Job("login-done")
                        self.posts.append(job)
                    except Exception as e:
                        traceback.print_exc()
                        job = Job("login-error")
                        job.data = e
                        self.posts.append(job)


                if job.name == "event":
                    self.process_event(job.data)

                if job.name == "update":
                    job = Job("spinner-start")
                    self.posts.append(job)
                    self.update()
                    job = Job("spinner-stop")
                    self.posts.append(job)

                if job.name == "refresh-friend-db-offline":
                    job = Job("spinner-start")
                    self.posts.append(job)
                    friends_api_instance = friends_api.FriendsApi(self.api_client)

                    n = 100
                    offset = 0
                    while True:
                        rl.inhibit()
                        try:
                            next = friends_api_instance.get_friends(n=n, offset=offset, offline="true")
                        except Exception as e:
                            print(str(e))
                            break
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
                    job = Job("spinner-stop")
                    self.posts.append(job)

                if job.name == "refresh-friend-db":

                    job = Job("spinner-start")
                    self.posts.append(job)

                    friends_api_instance = friends_api.FriendsApi(self.api_client)
                    n = 100
                    offset = 0
                    while True:
                        rl.inhibit()

                        try:
                            next = friends_api_instance.get_friends(n=n, offset=offset)
                        except Exception as e:
                            print("!!!")
                            print(str(e))
                            break

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
                    job = Job("spinner-stop")
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
                            try:
                                response = requests.get(v.user_icon, headers=REQUEST_DL_HEADER)
                                with open(key_path, 'wb') as f:
                                    f.write(response.content)
                            except:
                                failed_files.append(job.data)

                if job.name == "download-check-world-banner":
                    world = job.data
                    URL = world.thumbnail_image_url
                    print("Download world banner")
                    if URL:
                        key = extract_filename(URL)
                        key_path = os.path.join(WORLD_ICON_CACHE, key)
                        if key not in os.listdir(WORLD_ICON_CACHE):
                            try:
                                response = requests.get(URL, headers=REQUEST_DL_HEADER)
                                with open(key_path, 'wb') as f:
                                    f.write(response.content)
                            except:
                                failed_files.append(job.data)
                        job = Job("check-world-info-banner")
                        job.data = world
                        self.posts.append(job)

                if job.name == "download-check-user-banner":
                    v = job.data
                    URL = v.get_banner_url()
                    if URL:
                        key = extract_filename(URL)
                        key_path = os.path.join(USER_ICON_CACHE, key)
                        if key not in os.listdir(USER_ICON_CACHE):
                            try:
                                response = requests.get(URL, headers=REQUEST_DL_HEADER)
                                with open(key_path, 'wb') as f:
                                    f.write(response.content)
                            except:
                                failed_files.append(job.data)
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
                            try:
                                response = requests.get(v.current_avatar_thumbnail_image_url, headers=REQUEST_DL_HEADER)
                                with open(key_path, 'wb') as f:
                                    f.write(response.content)
                            except:
                                failed_files.append(job.data)

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
            if world.last_fetched and world.last_fetched.get() < WORLD_CACHE_DURATION:
                return world
        else:
            world = World()

        if not world.last_fetched:
            world.last_fetched = Timer()

        print("load world2")
        print(id)

        try:
            rl.inhibit()
            w = self.world_api.get_world(id)

            world.load_from_api_model(w)

            if world not in failed_files:
                job = Job("download-check-world-banner", world)
                self.jobs.append(job)
        except Exception as e:
            #raise
            print(str(e))

        world.last_fetched.set()


        #print(w)

        self.worlds[id] = world
        return world

    def load_location(self, location):

        try:
            print("LOAD LOCATION")
            if ":" not in location:
                self.instance_cache[location] = None
                return
            w_id, i_id = location.split(":")

            from urllib.parse import quote
            #i_id = quote(i_id)
            # if "~" in i_id:
            #     i_id = i_id.split("~")[0]
            #print((w_id, i_id))
            rl.inhibit()
            instance = self.instance_api.get_instance(w_id, i_id)
            if not instance:
                print("no instance gottin")
                self.instance_cache[location] = None
                return
            print("loaded instance")
            print(instance)
        except Exception as e:
            self.instance_cache[location] = None
            print("error loading instance")
            print(str(e))
            return

        self.instance_cache[location] = Instance(instance)



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


        self.set_default_size(1300, 650)
        self.set_title(APP_TITLE)

        self.login_toolbarview = Adw.ToolbarView()
        self.set_style(self.login_toolbarview, "view")
        self.login_header = Adw.HeaderBar()
        self.login_toolbarview.add_top_bar(self.login_header)
        self.login_clamp = Adw.Clamp()
        self.login_clamp.set_maximum_size(300)
        self.login_toolbarview.set_content(self.login_clamp)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(110)
        self.login_clamp.set_child(box)

        icon = Gtk.Image.new_from_file(f"{APP_ID}.svg")
        icon.set_pixel_size(100)
        icon.set_margin_bottom(30)
        box.append(icon)

        logo_box = Gtk.Box()
        icon = Gtk.Image.new_from_file("vrclogoblack.svg")
        icon.set_pixel_size(60)
        icon.set_margin_bottom(-10)

        #icon.set_margin_bottom(30)
        logo_box.append(icon)
        filler = Gtk.Box()
        logo_box.append(filler)
        box.append(logo_box)

        self.login_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_style(self.login_box, "linked")

        self.username_entry = Gtk.Entry(placeholder_text="Username or Email")
        self.login_box.append(self.username_entry)

        self.password_entry = Gtk.PasswordEntry(placeholder_text="Password")
        self.password_entry.set_show_peek_icon(True)
        self.login_box.append(self.password_entry)


        box.append(self.login_box)

        self.two_fa_entry = Gtk.Entry(placeholder_text="Two Factor Authentication Code")
        self.two_fa_entry.set_margin_top(10)
        self.two_fa_entry.set_visible(False)

        box.append(self.two_fa_entry)

        go_box = Gtk.Box()
        go_box.set_margin_top(10)
        filler = Gtk.Box()
        filler.set_hexpand(True)
        go_box.append(filler)
        self.login_spinner = Gtk.Spinner()
        self.login_spinner.set_margin_end(12)
        go_box.append(self.login_spinner)

        self.login_button = Gtk.Button(label="Login")
        self.login_button.connect("clicked", self.login_go)
        self.password_entry.connect("activate", self.login_go)
        self.username_entry.connect("activate", lambda x: self.password_entry.grab_focus())

        if os.path.exists(vrcz.cookie_file_path):
            self.login_spinner.start()
            self.username_entry.set_sensitive(False)
            self.password_entry.set_sensitive(False)
            self.login_button.set_sensitive(False)

        go_box.append(self.login_button)

        box.append(go_box)


        box2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box2.set_vexpand(True)
        box.append(box2)

        label = Gtk.Label(label="Created by Taiko2k.")
        label.set_justify(Gtk.Justification.CENTER)
        label.set_margin_bottom(3)
        self.set_style(label, "dim-label")
        box.append(label)

        label = Gtk.Label(label="Not affiliated with VRChat. Use at your own risk.")
        label.set_justify(Gtk.Justification.CENTER)
        label.set_margin_bottom(20)
        self.set_style(label, "dim-label")
        box.append(label)


        self.nav = Adw.NavigationSplitView()
        self.nav.set_max_sidebar_width(260)
        self.header = Adw.HeaderBar()

        action = Gio.SimpleAction.new("logout", None)
        action.connect("activate", self.activate_logout)
        self.add_action(action)

        action = Gio.SimpleAction.new("about", None)
        action.connect("activate", self.show_about)
        self.add_action(action)

        menu = Gio.Menu.new()

        item = Gio.MenuItem.new("Logout", "win.logout")
        menu.append_item(item)

        item = Gio.MenuItem.new(f"About {APP_TITLE}", "win.about")
        menu.append_item(item)

        self.menu = Gtk.MenuButton()
        self.menu.set_icon_name("open-menu-symbolic")
        self.popover = Gtk.PopoverMenu.new_from_model(menu)
        self.menu.set_popover(self.popover)
        self.header.pack_end(self.menu)

        l_menu = Gio.Menu.new()
        l_menu.append_item(item)


        self.l_menu = Gtk.MenuButton()
        self.l_menu.set_icon_name("open-menu-symbolic")
        self.l_popover = Gtk.PopoverMenu.new_from_model(l_menu)
        self.l_menu.set_popover(self.l_popover)
        self.login_header.pack_end(self.l_menu)

        self.n1 = Adw.NavigationPage()
        self.n0 = Adw.NavigationPage()
        self.t1 = Adw.ToolbarView()
        self.t1.add_top_bar(self.header)
        self.n1.set_child(self.t1)
        self.nav.set_content(self.n1)
        self.nav.set_sidebar(self.n0)

        #self.set_content(self.nav)
        self.login_toast_overlay = Adw.ToastOverlay()
        self.login_toast_overlay.set_child(self.login_toolbarview)
        self.set_content(self.login_toast_overlay)
        self.login_toast = Adw.Toast()
        self.login_toast.set_timeout(5)


        self.vsw1 = Adw.ViewSwitcher()
        self.vst1 = Adw.ViewStack()
        self.vsw1.set_stack(self.vst1)

        self.header.set_title_widget(self.vsw1)
        self.t1.set_content(self.vst1)

        self.spinner = Gtk.Spinner()
        #self.spinner.start()
        self.header.pack_end(self.spinner)


        # ------------------ Info page

        self.info_box_clamp = Adw.Clamp()
        self.info_box_clamp.set_maximum_size(1200)
        self.info_box_clamp.set_tightening_threshold(1000)

        self.vst1.add_titled_with_icon(self.info_box_clamp, "info", "Info", "user-info-symbolic")

        self.outer_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.outer_box.set_margin_start(10)
        self.outer_box.set_margin_end(10)
        self.info_box_clamp.set_child(self.outer_box)


        self.world_box_outer_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.world_box_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.world_box_holder.set_visible(False)
        self.world_box_holder.set_size_request(300, -1)
        self.world_box_holder.set_hexpand(True)
        self.world_box_outer_holder.set_margin_top(10)
        self.set_style(self.world_box_holder, "view")

        self.world_box_outer_scroll = Gtk.ScrolledWindow()
        #self.world_box_outer_scroll.set_vexpand(True)
        self.world_box_outer_scroll.set_child(self.world_box_outer_holder)
        self.world_box_outer_holder.append(self.world_box_holder)

        self.world_status_page = Adw.StatusPage()
        self.world_status_page.set_vexpand(True)
        self.world_status_page.set_hexpand(True)
        self.world_status_page.set_title("Offline")
        self.set_style(self.world_status_page, "view")

        self.world_status_page.set_icon_name("help-about-symbolic")
        self.world_box_outer_holder.append(self.world_status_page)



        self.world_banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.world_banner = Gtk.Picture()
        self.world_banner.set_can_shrink(True)
        self.world_banner.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.world_banner.set_size_request(-1, 170)
        self.world_banner.set_valign(Gtk.Align.START)
        self.world_banner.set_margin_top(10)

        self.world_banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        filler = Gtk.Box()
        filler.set_hexpand(True)
        self.world_banner_box.append(filler)
        self.world_banner_box.append(self.world_banner)
        filler = Gtk.Box()
        filler.set_hexpand(True)
        self.world_banner_box.append(filler)


        self.world_box_holder.append(self.world_banner_box)

        self.world_row1 = Gtk.ListBox()
        self.world_row1.set_selection_mode(Gtk.SelectionMode.NONE)

        self.world_name = Adw.ActionRow()
        self.world_name.set_subtitle("ExampleWorld")
        self.world_name.set_subtitle_selectable(True)
        self.world_name.set_title("World Name")
        self.set_style(self.world_name, "property")
        self.world_row1.append(self.world_name)

        self.world_desc = Adw.ActionRow()
        self.world_desc.set_subtitle("")
        self.world_desc.set_subtitle_selectable(True)
        self.world_desc.set_title("Description")
        self.set_style(self.world_desc, "property")
        self.world_row1.append(self.world_desc)

        self.world_box_holder.append(self.world_row1)

        box = Gtk.Box()

        self.world_row2 = Gtk.ListBox()
        self.world_row2.set_selection_mode(Gtk.SelectionMode.NONE)
        box.append(self.world_row2)

        self.world_c_date = Adw.ActionRow()
        self.world_c_date.set_subtitle("")
        self.world_c_date.set_subtitle_selectable(True)
        self.world_c_date.set_title("First Uploaded")
        self.set_style(self.world_c_date, "property")
        self.world_row2.append(self.world_c_date)

        self.world_row3 = Gtk.ListBox()
        self.world_row3.set_selection_mode(Gtk.SelectionMode.NONE)
        box.append(self.world_row3)

        self.world_author = Adw.ActionRow()
        self.world_author.set_subtitle("")
        self.world_author.set_subtitle_selectable(True)
        self.world_author.set_title("Author")
        self.set_style(self.world_author, "property")
        self.world_row3.append(self.world_author)

        self.world_box_holder.append(box)

        # INSTANCE --------------

        self.instance_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.instance_box.set_hexpand(True)
        self.instance_box.set_margin_top(8)
        self.set_style(self.instance_box, "view")
        self.world_box_outer_holder.append(self.instance_box)

        self.instance_row1 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)

        self.instancelb1 = Gtk.ListBox()
        self.instancelb1.set_selection_mode(Gtk.SelectionMode.NONE)
        self.instance_type = Adw.ActionRow()
        self.instance_type.set_subtitle("Unknown")
        self.instance_type.set_subtitle_selectable(True)
        self.instance_type.set_title("Instance Type")
        self.set_style(self.instance_type, "property")
        self.instancelb1.append(self.instance_type)
        self.instance_row1.append(self.instancelb1)

        self.instancelb2 = Gtk.ListBox()
        self.instancelb2.set_selection_mode(Gtk.SelectionMode.NONE)
        self.instance_count = Adw.ActionRow()
        self.instance_count.set_subtitle("Unknown")
        self.instance_count.set_subtitle_selectable(True)
        self.instance_count.set_title("Count")
        self.set_style(self.instance_count, "property")
        self.instancelb2.append(self.instance_count)
        self.instance_row1.append(self.instancelb2)


        self.instance_box.append(self.instance_row1)

        #filler = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        #filler.set_vexpand(True)
        #self.world_box_outer_holder.append(filler)


        self.info_box_holder = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.info_box_holder.set_hexpand(True)
        #self.info_box_holder.set_size_request(800, -1)


        self.info_box_holder.set_margin_top(10)
        self.set_style(self.info_box_holder, "view")

        self.info_box_outer_holder = Gtk.Box()
        self.info_box_outer_holder.append(self.info_box_holder)

        self.info_box_outer_scroll = Gtk.ScrolledWindow()
        #self.info_box_outer_scroll.set_vexpand(True)
        self.info_box_outer_scroll.set_child(self.info_box_outer_holder)

        #self.info_box_clamp.set_child(self.info_box_outer_scroll)


        self.outer_box.append(self.info_box_outer_scroll)
        self.info_spacer = Gtk.Box()
        self.info_spacer.set_size_request(10, -1)
        self.outer_box.append(self.info_spacer)
        self.outer_box.append(self.world_box_outer_scroll)



        self.row1and2 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.row1and2.set_hexpand(True)

        self.row1and2andpic = Gtk.Box()
        self.row1and2andpic.append(self.row1and2)

        self.banner_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.banner = Gtk.Picture()
        self.banner.set_size_request(-1, 170)
        self.banner.set_can_shrink(True)
        self.banner.set_valign(Gtk.Align.START)
        self.banner.set_margin_top(10)
        self.banner.set_content_fit(Gtk.ContentFit.CONTAIN)

        filler = Gtk.Box()
        filler.set_hexpand(True)
        self.banner_box.append(filler)
        self.banner_box.append(self.banner)
        filler = Gtk.Box()
        filler.set_hexpand(True)
        self.banner_box.append(filler)


        self.info_box_holder.append(self.banner_box)

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



        self.info_status = Adw.ActionRow()
        self.info_status.set_subtitle("Test")
        self.info_status.set_subtitle_selectable(True)
        self.info_status.set_title("Status")
        self.set_style(self.info_status, "property")
        self.row1and2.append(self.info_status)

        self.row4 = Gtk.ListBox()
        self.row4.set_selection_mode(Gtk.SelectionMode.NONE)

        self.info_box_holder.append(self.row4)

        self.info_bio = Adw.ActionRow()
        self.info_bio.set_subtitle("Example bio")
        self.info_bio.set_subtitle_selectable(True)
        self.info_bio.set_title("Bio")
        self.set_style(self.info_bio, "property")

        self.row4.append(self.info_bio)

        self.info_note = Adw.ActionRow()
        self.info_note.set_subtitle(" ")
        self.info_note.set_subtitle_selectable(True)
        self.info_note.set_title("Note")
        self.set_style(self.info_note, "property")

        self.row4.append(self.info_note)

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

        # friend search
        self.friend_search_entry = Gtk.SearchEntry()
        self.friend_search_entry.connect("search-changed", self.friend_search)
        self.friend_search_bar = Gtk.SearchBar()
        self.friend_search_bar.connect_entry(self.friend_search_entry)
        self.friend_list_box.append(self.friend_search_bar)
        self.friend_search_bar.set_child(self.friend_search_entry)
        self.friend_search_bar.set_search_mode(True)
        self.set_style(self.friend_search_bar, "view")
        self.set_style(self.friend_search_entry, "view")

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
        self.vst1.add_titled_with_icon(self.c4, "event", "Tracker", "find-location-symbolic")

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


        self.c3 = Adw.Clamp()
        self.c3.set_child(self.login_box)

        self.update_friend_list()


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
        self.selected_world_info = None
        if vrcz.user_object:
            self.set_profie_view(vrcz.user_object.id)
        GLib.timeout_add(20, self.heartbeat)

    def friend_search(self, a):
        if a.get_text():
            self.friend_list_view.set_single_click_activate(True)
        else:
            self.friend_list_view.set_single_click_activate(False)
        job = Job("update-friend-list")
        vrcz.posts.append(job)
    def show_about(self, a, b):
        dialog = Adw.AboutWindow(transient_for=self)
        dialog.set_application_name(APP_TITLE)
        dialog.set_version(VERSION)
        dialog.set_developer_name("Taiko2k")
        dialog.set_license_type(Gtk.License(Gtk.License.GPL_3_0))
        #dialog.set_comments("test")
        dialog.set_website("https://github.com/Tailko2k/Moonbeam")
        #dialog.set_issue_url("https://github.com/Tailko2k/Moonbeam/issues")
        #dialog.add_credit_section("Contributors", ["Name1 url"])
        #dialog.set_translator_credits("Name1 url")
        dialog.set_copyright("© 2024 Taiko2k captain.gxj@gmail.com\n\nThis application is not affiliated with VRChat."
                             " Use at your own risk!"
                             "\n\nVRChat and the VRChat logo are trademarks of VRChat Inc.")

        #dialog.set_developers(["Developer"])
        dialog.set_application_icon(
            "com.github.taiko2k.moonbeam")  # icon must be uploaded in ~/.local/share/icons or /usr/share/icons

        dialog.set_visible(True)
    def set_button_as_label(self, button):  # remove me
        style_context = button.get_style_context()
        style_context.add_provider(self.css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def set_style(self, target, name):
        style_context = target.get_style_context()
        style_context.add_class(name)

    def set_world_view_off(self, mode="offline"):
        self.world_box_holder.set_visible(False)
        self.world_status_page.set_visible(True)

        if mode == "offline":
            self.world_status_page.set_title("Offline")
        if mode == "private":
            self.world_status_page.set_title("Private Location")
        if mode == "loading":
            self.world_status_page.set_title("Loading...")


    def set_world_view(self, world):
        print("set world view")
        if not world:
            self.set_world_view_off()
            return

        self.world_box_holder.set_visible(True)
        self.world_status_page.set_visible(False)
        print(world)
        self.selected_world_info = world
        URL = world.thumbnail_image_url
        if URL and world not in failed_files:
            # print("URL")
            # print(URL)
            key = extract_filename(URL)
            print(key)
            key_path = os.path.join(WORLD_ICON_CACHE, key)
            if os.path.isfile(key_path):
                self.world_banner.set_filename(key_path)
            else:
                self.world_banner.set_resource("image-loading-symbolic")
                job = Job("download-check-world-banner")
                job.data = world
                vrcz.jobs.append(job)
        else:
            self.world_banner.set_filename(None)

        self.world_name.set_subtitle(world.name)
        self.world_desc.set_subtitle(world.description)
        if type(world.created_at) is str:
            self.world_c_date.set_subtitle(world.created_at)
        else:
            self.world_c_date.set_subtitle(str(world.created_at.strftime('%Y/%m/%d')))
        self.world_author.set_subtitle(world.author_name)
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
        if URL and p not in failed_files:
            # print("URL")
            # print(URL)
            key = extract_filename(URL)
            key_path = os.path.join(USER_ICON_CACHE, key)
            if os.path.isfile(key_path):
                self.banner.set_filename(key_path)
            else:
                self.banner.set_resource("image-loading-symbolic")
                job = Job("download-check-user-banner")
                job.data = p
                vrcz.jobs.append(job)
        else:
            self.banner.set_filename(None)

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

        self.info_status.set_subtitle(p.status_description)
        self.info_bio.set_subtitle(p.bio)

        text = p.note
        if not text:
            text = " "
        self.info_note.set_subtitle(text)

        print(p.location)
        world_id = vrcz.parse_world_id(p.location)

        if world_id:
            if world_id in vrcz.worlds:
                world = vrcz.worlds[world_id]
                self.set_world_view(world)
            else:
                self.set_world_view_off("loading")
                vrcz.load_world(world_id)
        else:
            if p.location == "private":
                self.set_world_view_off("private")
            else:
                self.set_world_view_off()

        self.set_instance_view(p)


    def set_instance_view(self, player):
        location = player.location
        if location == "private":
            self.instance_type.set_subtitle("Private")
            self.instance_count.set_subtitle(" ")
            return
        if location == "offline" or location == "unknown":
            self.instance_type.set_subtitle("Offline")
            self.instance_count.set_subtitle(" ")
            return
        self.instance_type.set_subtitle(" ")
        self.instance_count.set_subtitle(" ")

        instance = vrcz.instance_cache.get(location)

        if not instance:
            if location in vrcz.instance_cache:
                return
            if location not in vrcz.instances_to_load:
                vrcz.instances_to_load.append(location)
            return

        self.instance_type.set_subtitle(location_to_instance_type(location))
        self.instance_count.set_subtitle(f"{instance.n_users}/{instance.capacity}")


    def on_selected_friend_click(self, view, n):
        selected_item = self.ss.get_selected_item()
        if selected_item is not None:
            self.set_profie_view(selected_item.id)
        self.vst1.set_visible_child_name("info")
    def on_selected_friend_changed(self, selection, position, n_items):
        if self.friend_search_entry.get_text():
            return
        selected_item = selection.get_selected_item()
        if selected_item is not None:
            self.set_profie_view(selected_item.id)
        self.vst1.set_visible_child_name("info")


    def set_friend_row_data(self, id):

        row = self.friend_data.get(id)
        friend = vrcz.friend_objects.get(id)
        if friend is None and id == vrcz.user_object.id:
            friend = vrcz.user_object

        if row and friend:
            if not friend.location:
                friend.location = "unknown"
            # if friend.location == "offline":
            #     return
            # print("LOAD ROW --------")
            # print(f"friend: {friend.display_name}")
            # print(f"location: {friend.location}")
            # print(f"location: {friend.}")

            name = f"<b>{friend.display_name}</b>"
            if friend.id in vrcz.favorite_friends:
                name += " ⭐"
            row.name = name
            count = ""
            location = ""
            row.is_favorite = friend.id in vrcz.favorite_friends

            if not friend.location:
                location = "<small>Unknown</small>"
            elif friend.location == "offline":
                location = f"<span foreground=\"#aaaaaa\"><b><small>Offline</small></b></span>"
            elif friend.location == "private":
                location = f"<span foreground=\"#de7978\"><b><small>Private</small></b></span>"
            else:
                location = f"<span foreground=\"#aaaaaa\"><b><small>{friend.location.capitalize()}</small></b></span>"

            capacity = ""
            world_id = vrcz.parse_world_id(friend.location)
            if world_id:
                if world_id in vrcz.worlds:
                    world = vrcz.worlds[world_id]
                    location = f"<span foreground=\"#efb5f5\"><b><small>{world.name}</small></b></span>"
                else:
                    if world_id not in vrcz.worlds_to_load:
                        vrcz.worlds_to_load.append(world_id)

            # Determine type
            instance_type = location_to_instance_type(friend.location)

            text = ""
            if instance_type:
                text = f"<small><b><span background=\"#444444\"> {instance_type} </span></b></small> "

            # if count:
            #     text += f" <span foreground=\"#f2d37e\"><b><small>{count}/{capacity} </small></b></span> "

            text += location
            if row.location != text:
                row.location = text

            # if row.public_count != count:
            #     row.public_count = count



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
        if user.id:
            self.set_profie_view(user.id)
            self.vst1.set_visible_child_name("info")


    def heartbeat(self):
        update_friend_list = False
        update_friend_rows = False
        while vrcz.posts:
            post = vrcz.posts.pop(0)
            #print("post")
            #print(post.name)

            if post.name == "login-done":
                self.login_reset()
                self.main_view()
                self.login_spinner.stop()
            if post.name == "login-reset":
                self.login_reset()
                self.login_spinner.stop()
            if post.name == "login-error":
                e = post.data
                print(str(e))
                reason = False
                try:
                    print(e.reason)
                    reason = True
                except:
                    pass


                if "Invalid Username" in str(e):
                    self.login_toast.set_title("Invalid username, email or password")
                    self.login_toast_overlay.add_toast(self.login_toast)
                    self.login_reset()
                elif "2 Factor Authentication" in str(e):
                    self.login_toast.set_title("Please enter you 2FA code")
                    self.login_toast_overlay.add_toast(self.login_toast)
                    self.two_fa_entry.set_visible(True)
                    self.two_fa_entry.set_sensitive(True)
                    self.login_box.set_visible(False)
                    self.login_button.set_sensitive(True)
                else:
                    self.login_toast.set_title(str(e))
                    self.login_toast_overlay.add_toast(self.login_toast)
                    self.login_reset()

                self.login_spinner.stop()

            if post.name == "spinner-start":
                self.spinner.start()
            if post.name == "spinner-stop":
                self.spinner.stop()

            if post.name == "update-instance-info":
                if self.selected_user_info and self.selected_user_info.location == post.data:
                    self.set_instance_view(self.selected_user_info)
            if post.name == "check-user-info-banner":
                if self.selected_user_info and self.selected_user_info == post.data:
                    URL = self.selected_user_info.get_banner_url()
                    key = extract_filename(URL)
                    key_path = os.path.join(USER_ICON_CACHE, key)
                    if URL and os.path.isfile(key_path):
                        self.banner.set_filename(key_path)
                    else:
                        self.banner.set_filename(None)

            if post.name == "check-world-info-banner":
                if self.selected_world_info and self.selected_world_info == post.data:
                    self.set_world_view(self.selected_world_info)
                    # URL = self.selected_word_info.thumbnail_image_url
                    # key = extract_filename(URL)
                    # key_path = os.path.join(WORLD_ICON_CACHE, key)
                    # if URL and os.path.isfile(key_path):
                    #     self.world_banner.set_filename(key_path)
                    # else:
                    #     self.world_banner.set_filename(None)
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
                #print(event.type)


                label = Gtk.Label(label=format_time(event.timestamp))
                self.set_style(label, "dim-label")
                #self.set_style(label, "monospace")
                self.set_style(label, "caption")
                label.set_margin_end(3)
                label.set_size_request(70, -1)
                label.set_xalign(1)
                label.set_size_request(150, -1)
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
                                # print("aa")
                                # print(event.content)
                                # print(target)
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
                                    if not text:
                                        text = world_id

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

        GLib.timeout_add(500, self.heartbeat)

    def test2(self, button):
        #self.update_friend_list()
        job = Job("update-friend-list")

        # for k, v in self.friend_data.items():
        #     self.set_friend_row_data(k)

        vrcz.posts.append(job)

    def test3(self, button):
        job = Job("update")
        vrcz.jobs.append(job)
        button.set_sensitive(False)
        # if vrcz.update():
        #     button.set_sensitive(False)
        #     self.login_box.set_visible(True)
        # else:
        #     self.vst1.set_visible_child_name("login")


    def update_friend_list(self):

        search = unidecode(self.friend_search_entry.get_text()).lower()

        if search:
            self.friend_data.clear()
            self.friend_ls.remove_all()

        if vrcz.user_object and not search and vrcz.user_object.id not in self.friend_data:
            fd = FriendRow()
            fd.is_user = True
            fd.id = vrcz.user_object.id
            self.friend_data[vrcz.user_object.id] = fd
            self.set_friend_row_data(vrcz.user_object.id)
            self.friend_ls.append(fd)

        for k, v in vrcz.friend_objects.items():

            if search:
                if search not in unidecode(v.display_name).lower():
                    # if k in self.friend_data:
                    #     fd = self.friend_data[k]
                    #     del self.friend_data[k]
                    #     r, n = self.friend_ls.find(fd)
                    #     print((r, n))
                    #     if r:
                    #         self.friend_ls.remove(n)
                    continue

            if k not in self.friend_data:
                fd = FriendRow()

            # else:
            #     fd = self.friend_data[k]
                fd.id = k
                #fd.is_favorite = k in vrcz.favorite_friends
                self.friend_data[k] = fd
                self.set_friend_row_data(k)
                self.friend_ls.append(fd)

        def get_weight(row):
            if row.is_user:
                return -1

            if row.is_favorite:
                if row.status == 4:
                    return 1
                if row.status == 2:
                    return 2
                if row.status == 5:
                    return 3
                if row.status == 3:
                    return 4

            if row.status == 4:
                return 10
            if row.status == 2:
                return 20
            if row.status == 5:
                return 30
            if row.status == 3:
                return 40
            if row.status == 1:
                return 50
            return 60


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

    def login_view(self):
        self.set_content(self.login_toast_overlay)
    def main_view(self):
        self.set_content(self.nav)
    def login_reset(self):
        self.username_entry.set_sensitive(True)
        self.password_entry.set_sensitive(True)
        self.login_button.set_sensitive(True)
        self.login_box.set_visible(True)
        self.two_fa_entry.set_visible(False)
    def login_go(self, button):
        username = self.username_entry.get_text()
        password = self.password_entry.get_text()
        if not username or not password:
            self.login_toast.set_title("Missing username or password")
            self.login_toast_overlay.add_toast(self.login_toast)
            return
        code = self.two_fa_entry.get_text()

        self.username_entry.set_sensitive(False)
        self.password_entry.set_sensitive(False)
        self.login_button.set_sensitive(False)

        self.login_spinner.start()
        job = Job("login")
        job.data = (username, password, code)
        vrcz.jobs.append(job)

    def activate_logout(self, a, b):
        vrcz.logout()
        self.login_reset()
        self.login_view()
        vrcz.initial_update = False
        if vrcz.ws:
            vrcz.ws.close()
            vrcz.ws = None

class MOONBEAM(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.win = None
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self.win = MainWindow(application=app)
        self.win.present()


app = MOONBEAM(application_id=APP_ID)
app.run()

# if vrcz.user_object:
#     vrcz.user_object.location = "offline"
#     vrcz.user_object.status = "offline"
# for k, v in vrcz.friend_objects.items():
#     v.location = "offline"
#     v.status = "offline"
if vrcz.online_friend_db_update_timer:
    vrcz.online_friend_db_update_timer.set()
vrcz.save_app_data()
RUNNING = False

