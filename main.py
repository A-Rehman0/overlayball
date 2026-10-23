"""Launcher UI: pick images, grant overlay permission, start the floating-ball service."""
import os
import re
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from jnius import autoclass
from android import activity, AndroidService
from android.permissions import request_permissions

PythonActivity = autoclass("org.kivy.android.PythonActivity")
Intent = autoclass("android.content.Intent")
Settings = autoclass("android.provider.Settings")
Uri = autoclass("android.net.Uri")
BitmapFactory = autoclass("android.graphics.BitmapFactory")
Options = autoclass("android.graphics.BitmapFactory$Options")
CompressFormat = autoclass("android.graphics.Bitmap$CompressFormat")
FileOutputStream = autoclass("java.io.FileOutputStream")

act = PythonActivity.mActivity
REQ = 4711
REFS = act.getFilesDir().getAbsolutePath() + "/refs"
MAX_SIDE = 1600


def natural_key(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def display_name(uri):
    try:
        c = act.getContentResolver().query(uri, None, None, None, None)
        try:
            if c is not None and c.moveToFirst():
                i = c.getColumnIndex("_display_name")
                if i >= 0:
                    return c.getString(i)
        finally:
            if c is not None:
                c.close()
    except Exception:
        pass
    return uri.getLastPathSegment() or "image"


def save_scaled(uri, dst_base):
    """Decode with sub-sampling (low RAM), then store as JPEG/PNG in app storage."""
    cr = act.getContentResolver()
    o = Options()
    o.inJustDecodeBounds = True
    s = cr.openInputStream(uri)
    BitmapFactory.decodeStream(s, None, o)
    s.close()
    sample = 1
    while max(o.outWidth, o.outHeight) // (sample * 2) >= MAX_SIDE:
        sample *= 2
    o2 = Options()
    o2.inSampleSize = sample
    s = cr.openInputStream(uri)
    bmp = BitmapFactory.decodeStream(s, None, o2)
    s.close()
    if bmp is None:
        return False
    png = bmp.hasAlpha()
    out = FileOutputStream(dst_base + (".png" if png else ".jpg"))
    bmp.compress(CompressFormat.PNG if png else CompressFormat.JPEG, 92, out)
    out.close()
    bmp.recycle()
    return True


class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", padding=30, spacing=20, **kw)
        self.status = Label(text=self.count_text(), font_size="18sp")
        b1 = Button(text="1. Select reference images", font_size="18sp")
        b2 = Button(text="2. Start floating ball", font_size="18sp")
        b3 = Button(text="Stop floating ball", font_size="18sp")
        b1.bind(on_release=lambda *_: self.pick())
        b2.bind(on_release=lambda *_: self.start())
        b3.bind(on_release=lambda *_: self.stop())
        for w in (self.status, b1, b2, b3):
            self.add_widget(w)
        activity.bind(on_activity_result=self.on_result)
        request_permissions(["android.permission.POST_NOTIFICATIONS"])

    def count_text(self):
        n = len(os.listdir(REFS)) if os.path.isdir(REFS) else 0
        return f"{n} image(s) ready"

    def say(self, t):
        Clock.schedule_once(lambda dt: setattr(self.status, "text", t))

    def pick(self):
        i = Intent(Intent.ACTION_OPEN_DOCUMENT)
        i.addCategory(Intent.CATEGORY_OPENABLE)
        i.setType("image/*")
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, True)
        act.startActivityForResult(i, REQ)

    def on_result(self, req, res, intent):
        if req != REQ or res != -1 or intent is None:
            return
        uris = []
        clip = intent.getClipData()
        if clip is not None:
            uris = [clip.getItemAt(k).getUri() for k in range(clip.getItemCount())]
        elif intent.getData() is not None:
            uris = [intent.getData()]
        threading.Thread(target=self.import_images, args=(uris,), daemon=True).start()

    def import_images(self, uris):
        os.makedirs(REFS, exist_ok=True)
        for f in os.listdir(REFS):
            os.remove(os.path.join(REFS, f))
        items = sorted(((display_name(u), u) for u in uris), key=lambda x: natural_key(x[0]))
        done = 0
        for n, (_, u) in enumerate(items):
            self.say(f"Importing {n + 1}/{len(items)} ...")
            try:
                done += save_scaled(u, os.path.join(REFS, f"{n:04d}"))
            except Exception as e:
                print("import failed:", e)
        self.say(f"{done} image(s) ready")

    def start(self):
        if not Settings.canDrawOverlays(act):
            self.say("Allow 'Display over other apps', then come back and press Start")
            act.startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                                     Uri.parse("package:" + act.getPackageName())))
            return
        if not os.path.isdir(REFS) or not os.listdir(REFS):
            self.say("Select images first")
            return
        AndroidService("Overlay Ball", "Reference overlay running").start(REFS)
        act.moveTaskToBack(True)

    def stop(self):
        AndroidService("Overlay Ball", "").stop()
        self.say("Stopped")


class OverlayApp(App):
    def build(self):
        return Root()


OverlayApp().run()
