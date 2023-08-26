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


APP_TITLE = "Moonbeam VRC"
VERSION = "v0.1 indev"
USER_AGENT = 'taiko2k-moonbeam'
REQUEST_DL_HEADER = {
    'User-Agent': USER_AGENT,
}

AUTH_FILE = 'auth_data.pkl'
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
    "last_platform", "current_avatar_thumbnail_image_url"
]

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


class FriendRow(GObject.Object):
    name = GObject.Property(type=str, default='')
    status = GObject.Property(type=int, default=0)
    mini_icon_filepath = GObject.Property(type=str, default='')

    def __init__(self):
        super().__init__()
        self.name = ""
        self.mini_icon_filepath = None
        self.status = 0
        self.is_user = False

class Friend():
    def __init__(self, **kwargs):
        for item in COPY_FRIEND_PROPERTIES:
            setattr(self, item, None)
        for key, value in kwargs.items():
            setattr(self, key, value)


class Job:
    def __init__(self, name: str, data=None):
        self.name = name
        self.data = data

test = Job("a", "b")

class Event:
    def __init__(self, type="", content=""):
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


def parse_world_info(s):
    world = Instance()

    # Split on '&'
    parts = s.split('&')

    for part in parts:
        if 'worldId' in part:
            world.world_id = part.split('=')[1]
        elif 'instanceId' in part:
            instance_parts = part.split('=')[1].split('~')
            world.instance_id = instance_parts[0]

            for instance_part in instance_parts[1:]:
                if 'hidden' in instance_part:
                    world.instance_type = 'hidden'
                    world.owner_id = instance_part.split('(')[1].rstrip(')')
                elif 'private' in instance_part:
                    world.instance_type = 'private'
                    world.owner_id = instance_part.split('(')[1].rstrip(')')
                elif 'canRequestInvite' in instance_part:
                    world.can_request_invite = True
                elif 'region' in instance_part:
                    world.region = instance_part.split('(')[1].rstrip(')')
                elif 'nonce' in instance_part:
                    world.nonce = instance_part.split('(')[1].rstrip(')')

    return world

class VRCZ:

    def __init__(self):
        self.logged_in = False

        self.current_user_name = ""  # in-game name
        self.friend_id_list = []
        self.friend_objects = {}
        self.user_object = None
        self.web_thread = None

        self.error_log = []  # in event of any error, append human-readable string explaining error
        self.api_client = vrchatapi.ApiClient()
        self.api_client.user_agent = USER_AGENT
        self.auth_api = authentication_api.AuthenticationApi(self.api_client)
        self.cookie_file_path = 'cookie_data'

        self.jobs = []
        self.posts = []

        self.events = []

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
                    print("-----------")
                    print(event.content["location"])
                    print(event.content["travelingToLocation"])
                    print(event.content["user"])
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

    def save_cookies(self):
        cookie_jar = LWPCookieJar(filename=self.cookie_file_path)
        for cookie in self.api_client.rest_client.cookie_jar:
            cookie_jar.set_cookie(cookie)
        cookie_jar.save()

    def load_cookies(self):
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
                print(d)
                if "friends" in d:
                    for k, v in d["friends"].items():
                        friend = Friend(**v)
                        self.friend_objects[k] = friend
                if "self" in d:
                    self.user_object = Friend(**d["self"])


    def save_app_data(self):
        self.save_cookies()
        d = {}
        friends = {}
        for k, v in self.friend_objects.items():
            friends[k] = v.__dict__

        d["friends"] = friends
        d["self"] = self.user_object.__dict__
        with open(DATA_FILE, 'wb') as file:
            pickle.dump(d, file)


    def sign_in_step1(self, username, password):
        self.api_client.configuration.username = username
        self.api_client.configuration.password = password

        try:
            user = self.auth_api.get_current_user()
            self.logged_in = True
            self.current_user_name = user.display_name
        except UnauthorizedException as e:
            if "2 Factor Authentication" in e.reason:
                print("2FA required. Please provide the code sent to your email.")
                return
            else:
                print(f"Error during authentication: {e}")
                self.error_log.append(f"Error during authentication: {e}")
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
            setattr(t, key, getattr(r, key))
        job = Job("download-check-user-icon", t)
        self.jobs.append(job)
        job = Job("download-check-user-avatar-thumbnail", t)
        self.jobs.append(job)

        self.friend_objects[r.id] = t

    def update(self):

        # Try authenticate
        try:
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

        if os.path.exists(AUTH_FILE):
            os.remove(AUTH_FILE)

        self.__init__()

    def worker(self):
        while RUNNING:
            if self.jobs:
                job = self.jobs.pop(0)
                print("doing job")
                print(job.name)

                if job.name == "event":
                    self.process_event(job.data)

                if job.name == "refresh-friend-db-offline":

                    friends_api_instance = friends_api.FriendsApi(self.api_client)

                    print("COOLDOWN")
                    time.sleep(2)
                    n = 100
                    offset = 0
                    while True:
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
                        print("COOLDOWN")
                        time.sleep(10)

                    self.save_app_data()
                    job = Job("update-friend-rows")
                    self.posts.append(job)
                    job = Job("update-friend-list")
                    self.posts.append(job)

                if job.name == "refresh-friend-db":
                    friends_api_instance = friends_api.FriendsApi(self.api_client)
                    print("COOLDOWN")
                    time.sleep(3)
                    n = 100
                    offset = 0
                    while True:
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
                        print("COOLDOWN")

                        time.sleep(10)

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
                            time.sleep(0.5)
                            with open(key_path, 'wb') as f:
                                f.write(response.content)

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
                            time.sleep(0.5)
                            with open(key_path, 'wb') as f:
                                f.write(response.content)


            time.sleep(0.1)




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

        self.set_default_size(1000, 500)
        self.set_title(APP_TITLE)

        self.nav = Adw.NavigationSplitView()
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


        # ---- Info page
        self.info_list = Gtk.ListBox()
        self.info_list.set_selection_mode(Gtk.SelectionMode.NONE)
        style_context = self.info_list.get_style_context()
        style_context.add_class('boxed-ist')

        self.c1 = Adw.Clamp()

        self.info_box1 = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.info_box_header = Gtk.Box()
        self.info_box1.append(self.info_box_header)

        self.info_box_header_title = Gtk.Label(label="WIP")
        self.info_box_header_title.set_selectable(True)
        self.set_style(self.info_box_header_title, "title-2")
        self.info_box_header.set_margin_top(6)
        self.info_box_header.append(self.info_box_header_title)

        #self.c1.set_child(self.info_list)
        self.c1.set_child(self.info_box1)

        self.vst1.add_titled_with_icon(self.c1, "info", "Player Info", "user-info-symbolic")

        self.info_name = Adw.ActionRow()
        self.info_name.set_subtitle("Test")
        self.info_name.set_title("Test3")
        self.set_style(self.info_name, "property")
        self.info_list.append(self.info_name)

        # ------


        style_context = self.get_style_context()
        style_context.add_class('devel')



        #self.set_titlebar()


        # Friend list box
        self.friend_list_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.friend_list_box.set_size_request(220, -1)
        #self.outer_box.append(self.friend_list_box)

        self.n0.set_child(self.friend_list_box)

        self.friend_data = {}
        self.friend_list_view = Gtk.ListView()
        self.friend_list_scroll = Gtk.ScrolledWindow()
        self.friend_list_scroll.set_vexpand(True)
        self.friend_list_scroll.set_child(self.friend_list_view)
        self.friend_list_box.append(self.friend_list_scroll)
        self.friend_ls = Gio.ListStore(item_type=FriendRow)

        ss = Gtk.SingleSelection()
        ss.set_model(self.friend_ls)
        self.friend_list_view.set_model(ss)

        factory = Gtk.SignalListItemFactory()

        def f_setup(fact, item):

            holder = Gtk.Box()
            holder.set_margin_top(2)
            holder.set_margin_bottom(2)
            holder.set_margin_start(4)

            icon = UserIconDisplay()
            icon.set_size_request(43, 43)
            holder.append(icon)

            # image = Gtk.Image()
            # image.set_size_request(40, 40)
            # holder.append(image)

            label = Gtk.Label(halign=Gtk.Align.START)
            label.set_selectable(False)
            label.set_margin_start(9)
            label.set_use_markup(True)

            holder.append(label)

            item.set_child(holder)
            item.label = label
            # item.image = image
            item.icon = icon

        factory.connect("setup", f_setup)

        def f_bind(fact, row):
            friend = row.get_item()
            #row.label.set_label(friend.name)

            friend.bind_property("name",
                          row.label, "label",
                          GObject.BindingFlags.SYNC_CREATE)

            # friend.bind_property("mini_icon_filepath",
            #               row.image, "file",
            #               GObject.BindingFlags.SYNC_CREATE)

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
        self.password_entry = Gtk.Entry(placeholder_text="Password", visibility=False)
        self.stage1_box.append(self.username_entry)
        self.stage1_box.append(self.password_entry)


        self.request_code_button = Gtk.Button(label="Request Code")
        self.request_code_button.set_margin_bottom(30)
        self.request_code_button.connect("clicked", self.activate_get_code)
        self.stage1_box.append(self.request_code_button)
        self.login_box.append(self.stage1_box)

        self.stage2_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stage2_box.set_visible(False)



        self.two_fa_entry = Gtk.Entry(placeholder_text="2FA Code")
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

        GLib.timeout_add(900, self.heartbeat)

        # self.user_window = UserInfoWindow()
        # self.user_window.set_transient_for(self)
        # self.user_window.set_modal(True)
        # self.user_window.set_destroy_with_parent(True)
        # self.user_window.show()

    def set_style(self, target, name):
        style_context = target.get_style_context()
        style_context.add_class(name)
    def set_friend_row_data(self, id):

        row = self.friend_data.get(id)
        friend = vrcz.friend_objects.get(id)
        if friend is None and id == vrcz.user_object.id:
            friend = vrcz.user_object
        if row and friend:
            pass
            old = row.name
            row.name = f"<b>{friend.display_name}</b>"

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
                    row.mini_icon_filepath = key_path
            elif friend.current_avatar_thumbnail_image_url:
                key = extract_filename(friend.current_avatar_thumbnail_image_url)
                if key:
                    key_path = os.path.join(USER_ICON_CACHE, key)
                    row.mini_icon_filepath = key_path


    def heartbeat(self):
        update_friend_list = False
        update_friend_rows = False
        while vrcz.posts:
            post = vrcz.posts.pop(0)
            print("post")
            print(post.name)
            if post.name == "update-friend-list":
                update_friend_list = True
            if post.name == "update-friend-rows":
                update_friend_rows = True
            if post.name == "event":
                # bm1
                event = post.data
                if event.type.startswith("friend-"):
                    if event.type == "friend-active":
                        continue
                    if event.type == "friend-update":
                        continue
                    if self.events_empty:
                        self.events_empty = False
                        self.event_box_holder.remove(self.events_empty_status)
                        self.event_box_holder.append(self.event_scroll)


                    box = Gtk.Box()
                    box.set_margin_bottom(3)
                    print(event.type)


                    #label = Gtk.Label(label=post.data.type)
                    label = Gtk.Label(label=format_time(event.timestamp))
                    self.set_style(label, "dim-label")
                    label.set_margin_end(5)
                    box.append(label)

                    user = event.subject
                    if user:
                        label = Gtk.Label()
                        if user.location != "offline":
                            label.set_markup(f"<span foreground=\"#16f2ca\" weight=\"bold\">{user.display_name}</span>")
                        else:
                            label.set_markup(f"<span weight=\"bold\">{user.display_name}</span>")
                            self.set_style(label, "dim-label")

                        label.set_margin_end(5)
                        box.append(label)

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
                                target = user.location
                                if target == "private" or not target:
                                    label = Gtk.Label()
                                    label.set_markup(f"arrived at a hidden location")
                                    label.set_margin_end(5)
                                    box.append(label)
                                else:
                                    label = Gtk.Label()
                                    label.set_markup(f"arrived at")
                                    label.set_margin_end(5)
                                    box.append(label)

                                    label = Gtk.Label()
                                    label.set_markup(f"{target}...")
                                    label.set_margin_end(5)
                                    box.append(label)


                    self.event_box.prepend(box)
                    job = Job("update-friend-list")
                    vrcz.posts.append(job)

        if update_friend_rows:
            for k, v in self.friend_data.items():
                self.set_friend_row_data(k)
        if update_friend_list:
            self.update_friend_list()

        GLib.timeout_add(1000, self.heartbeat)

    def test2(self, button):
        #self.update_friend_list()
        job = Job("update-friend-list")

        # for k, v in self.friend_data.items():
        #     self.set_friend_row_data(k)

        vrcz.posts.append(job)

    def test3(self, button):
        if vrcz.update():
            self.login_box.set_visible(True)

    def update_friend_list(self):

        self.friend_ls.remove_all()
        #print(vrcz.friend_objects)
        if vrcz.user_object:
            if vrcz.user_object.id not in self.friend_data:
                fd = FriendRow()
                fd.is_user = True
                self.friend_data[vrcz.user_object.id] = fd
            fd = self.friend_data[vrcz.user_object.id]
            self.set_friend_row_data(vrcz.user_object.id)
            self.friend_ls.append(fd)

        for k, v in vrcz.friend_objects.items():
            if k not in self.friend_data:
                fd = FriendRow()
                self.friend_data[k] = fd
            fd = self.friend_data[k]
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
        try:
            vrcz.sign_in_step1(username, password)
            self.stage3_box.set_visible(False)
            self.stage2_box.set_visible(True)
            self.stage1_box.set_visible(False)
        except ValueError as e:
            print(e)

    def activate_verify_code(self, button):
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


class VRCZAPP(Adw.Application):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.connect('activate', self.on_activate)

    def on_activate(self, app):
        self.win = MainWindow(application=app)
        self.win.present()


app = VRCZAPP(application_id="com.github.taiko2k.moonbeam")
app.run(sys.argv)
RUNNING = False
time.sleep(2)