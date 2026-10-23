"""Runs in its own process: draws the reference image + floating ball over all apps."""
import os
import time
import traceback

from jnius import autoclass, PythonJavaClass, java_method

PythonService = autoclass("org.kivy.android.PythonService")
Context = autoclass("android.content.Context")
LP = autoclass("android.view.WindowManager$LayoutParams")
PixelFormat = autoclass("android.graphics.PixelFormat")
Gravity = autoclass("android.view.Gravity")
GradientDrawable = autoclass("android.graphics.drawable.GradientDrawable")
Color = autoclass("android.graphics.Color")
TextView = autoclass("android.widget.TextView")
ImageView = autoclass("android.widget.ImageView")
ScaleType = autoclass("android.widget.ImageView$ScaleType")
LinearLayout = autoclass("android.widget.LinearLayout")
SeekBar = autoclass("android.widget.SeekBar")
Button = autoclass("android.widget.Button")
Handler = autoclass("android.os.Handler")
Looper = autoclass("android.os.Looper")
BitmapFactory = autoclass("android.graphics.BitmapFactory")
Options = autoclass("android.graphics.BitmapFactory$Options")
SystemClock = autoclass("android.os.SystemClock")

svc = PythonService.mService
REFS = os.environ.get("PYTHON_SERVICE_ARGUMENT") or (svc.getFilesDir().getAbsolutePath() + "/refs")

# opacity is applied on the WINDOW (not the view) and capped at 0.8:
# Android 12+ blocks touches to apps underneath if an overlay is more opaque than 0.8
MIN_A, MAX_A = 5, 80

files = sorted(
    (os.path.join(REFS, f) for f in os.listdir(REFS) if f.lower().endswith((".jpg", ".png"))),
)
st = {"i": 0, "on": True, "panel": False, "alpha": 0.5, "down": 0, "dx": 0, "dy": 0,
      "x0": 0, "y0": 0, "moved": False, "t": 0, "long": False}

handler = Handler(Looper.getMainLooper())
_keep = []


class _Run(PythonJavaClass):
    __javainterfaces__ = ["java/lang/Runnable"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @java_method("()V")
    def run(self):
        try:
            self.fn()
        except Exception:
            traceback.print_exc()


def ui(fn):
    r = _Run(fn)
    _keep.append(r)
    del _keep[:-20]
    handler.post(r)


class _Click(PythonJavaClass):
    __javainterfaces__ = ["android/view/View$OnClickListener"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @java_method("(Landroid/view/View;)V")
    def onClick(self, v):
        self.fn()


class _Seek(PythonJavaClass):
    __javainterfaces__ = ["android/widget/SeekBar$OnSeekBarChangeListener"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @java_method("(Landroid/widget/SeekBar;IZ)V")
    def onProgressChanged(self, s, p, user):
        self.fn(p)

    @java_method("(Landroid/widget/SeekBar;)V")
    def onStartTrackingTouch(self, s):
        pass

    @java_method("(Landroid/widget/SeekBar;)V")
    def onStopTrackingTouch(self, s):
        pass


class _Touch(PythonJavaClass):
    __javainterfaces__ = ["android/view/View$OnTouchListener"]
    __javacontext__ = "app"

    def __init__(self, fn):
        super().__init__()
        self.fn = fn

    @java_method("(Landroid/view/View;Landroid/view/MotionEvent;)Z")
    def onTouch(self, v, e):
        return self.fn(e)


def build():
    wm = svc.getSystemService(Context.WINDOW_SERVICE)
    dm = svc.getResources().getDisplayMetrics()
    d, W, H = dm.density, dm.widthPixels, dm.heightPixels
    dp = lambda v: int(v * d)
    BALL, PANEL_W, PANEL_H = dp(56), dp(250), dp(210)
    keep = []  # listeners must stay referenced

    # ---------- 1. reference image (click-through) ----------
    img = ImageView(svc)
    img.setScaleType(ScaleType.FIT_CENTER)
    ip = LP(-1, -1, LP.TYPE_APPLICATION_OVERLAY,
            LP.FLAG_NOT_FOCUSABLE | LP.FLAG_NOT_TOUCHABLE | LP.FLAG_LAYOUT_IN_SCREEN | LP.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT)
    ip.alpha = st["alpha"]
    wm.addView(img, ip)
    cache = {"bmp": None}

    def show(i):
        if not files:
            return
        st["i"] = i % len(files)
        o = Options()
        o.inJustDecodeBounds = True
        BitmapFactory.decodeFile(files[st["i"]], o)
        s = 1
        while o.outWidth // (s * 2) >= W and o.outHeight // (s * 2) >= H:
            s *= 2
        o2 = Options()
        o2.inSampleSize = s
        bmp = BitmapFactory.decodeFile(files[st["i"]], o2)
        img.setImageBitmap(bmp)
        if cache["bmp"] is not None:
            cache["bmp"].recycle()
        cache["bmp"] = bmp
        counter.setText(f"{st['i'] + 1} / {len(files)}")

    # ---------- 2. control panel ----------
    panel = LinearLayout(svc)
    panel.setOrientation(1)
    panel.setPadding(dp(14), dp(12), dp(14), dp(12))
    bg = GradientDrawable()
    bg.setColor(Color.parseColor("#E6202020"))
    bg.setCornerRadius(float(dp(18)))
    panel.setBackground(bg)

    counter = TextView(svc)
    counter.setTextColor(Color.WHITE)
    counter.setGravity(Gravity.CENTER)
    title = TextView(svc)
    title.setTextColor(Color.WHITE)
    title.setText("Opacity")

    def on_seek(p):
        st["alpha"] = (p + MIN_A) / 100.0
        ip.alpha = st["alpha"]
        wm.updateViewLayout(img, ip)

    seek = SeekBar(svc)
    seek.setMax(MAX_A - MIN_A)
    seek.setProgress(int(st["alpha"] * 100) - MIN_A)
    sl = _Seek(on_seek)
    keep.append(sl)
    seek.setOnSeekBarChangeListener(sl)

    row = LinearLayout(svc)
    row.setOrientation(0)

    def mk(text, fn):
        b = Button(svc)
        b.setText(text)
        c = _Click(fn)
        keep.append(c)
        b.setOnClickListener(c)
        row.addView(b, LinearLayout.LayoutParams(0, -2, 1.0))
        return b

    mk("◀", lambda: show(st["i"] - 1))
    mk("▶", lambda: show(st["i"] + 1))

    def quit_all():
        try:
            for v in (img, panel, ball):
                wm.removeView(v)
        finally:
            svc.stopSelf()
            os._exit(0)

    quit_btn = Button(svc)
    quit_btn.setText("Quit")
    qc = _Click(quit_all)
    keep.append(qc)
    quit_btn.setOnClickListener(qc)

    panel.addView(counter)
    panel.addView(title)
    panel.addView(seek)
    panel.addView(row)
    panel.addView(quit_btn)
    panel.setVisibility(8)  # GONE

    pp = LP(PANEL_W, -2, LP.TYPE_APPLICATION_OVERLAY,
            LP.FLAG_NOT_FOCUSABLE | LP.FLAG_LAYOUT_NO_LIMITS, PixelFormat.TRANSLUCENT)
    pp.gravity = Gravity.TOP | Gravity.LEFT
    wm.addView(panel, pp)

    # ---------- 3. floating ball ----------
    ball = TextView(svc)
    ball.setText("◐")
    ball.setTextSize(24.0)
    ball.setTextColor(Color.WHITE)
    ball.setGravity(Gravity.CENTER)
    shape = GradientDrawable()
    shape.setShape(1)  # OVAL
    shape.setStroke(dp(2), Color.WHITE)
    ball.setBackground(shape)
    GREEN, RED = Color.parseColor("#CC2E7D32"), Color.parseColor("#CCB71C1C")
    shape.setColor(GREEN)

    bp = LP(BALL, BALL, LP.TYPE_APPLICATION_OVERLAY,
            LP.FLAG_NOT_FOCUSABLE | LP.FLAG_LAYOUT_NO_LIMITS, PixelFormat.TRANSLUCENT)
    bp.gravity = Gravity.TOP | Gravity.LEFT
    bp.x, bp.y = W - BALL - dp(8), H // 3
    wm.addView(ball, bp)

    def toggle_panel():
        st["panel"] = not st["panel"]
        if st["panel"]:
            pp.x = max(0, min(bp.x, W - PANEL_W))
            pp.y = bp.y + BALL + dp(8)
            if pp.y + PANEL_H > H:
                pp.y = max(0, bp.y - PANEL_H - dp(8))
            wm.updateViewLayout(panel, pp)
        panel.setVisibility(0 if st["panel"] else 8)

    def toggle_overlay():
        st["on"] = not st["on"]
        img.setVisibility(0 if st["on"] else 8)
        shape.setColor(GREEN if st["on"] else RED)

    def on_touch(e):
        a = e.getAction()
        if a == 0:  # DOWN
            st.update(dx=e.getRawX(), dy=e.getRawY(), x0=bp.x, y0=bp.y,
                      moved=False, t=SystemClock.uptimeMillis())
        elif a == 2:  # MOVE
            mx, my = e.getRawX() - st["dx"], e.getRawY() - st["dy"]
            if abs(mx) > dp(8) or abs(my) > dp(8):
                st["moved"] = True
            if st["moved"]:
                bp.x = int(max(0, min(W - BALL, st["x0"] + mx)))
                bp.y = int(max(0, min(H - BALL, st["y0"] + my)))
                wm.updateViewLayout(ball, bp)
                if st["panel"]:
                    toggle_panel()
        elif a == 1 and not st["moved"]:  # UP without drag
            if SystemClock.uptimeMillis() - st["t"] > 600:
                toggle_overlay()
            else:
                toggle_panel()
        return True

    tl = _Touch(on_touch)
    keep.append(tl)
    ball.setOnTouchListener(tl)

    _keep.extend(keep)
    show(0)


ui(build)
while True:          # keep the service process alive
    time.sleep(3600)
