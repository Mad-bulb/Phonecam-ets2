# Phone camera for ETS2 (v1)

Phone (ARCore 6DoF) -> UDP over Wi-Fi -> opentrack on Windows -> ETS2 head tracking.

Untested: this was written without being able to compile or run it, so expect to fix small build errors.

## 1. Build the Android app

1. Android Studio -> New Project -> **Empty Views Activity**. Language Kotlin, package name `com.example.phonecam`, Minimum SDK 24.
2. Replace the generated `MainActivity.kt` with the one in this folder.
3. In `app/build.gradle.kts`, add to `dependencies { ... }`:
   `implementation("com.google.ar:core:1.45.0")`
4. In `AndroidManifest.xml`:
   - Above `<application>` add:
     ```xml
     <uses-permission android:name="android.permission.CAMERA" />
     <uses-permission android:name="android.permission.INTERNET" />
     <uses-feature android:name="android.hardware.camera.ar" android:required="true" />
     ```
   - Inside `<application>` add:
     ```xml
     <meta-data android:name="com.google.ar.core" android:value="required" />
     ```
   - On the `<activity>` tag add `android:screenOrientation="portrait"`.
5. Plug in the phone (USB debugging on) and press Run. Install "Google Play Services for AR" if it asks.

## 2. Test the data stream (no game yet)

1. On the PC, find its IP: `ipconfig` -> IPv4 address. Phone and PC must be on the same Wi-Fi (not guest Wi-Fi).
2. Allow UDP 4242 inbound in Windows Firewall.
3. Run `python udp_check.py`.
4. In the app, type the PC IP, tap **Start sending**, move the phone slowly until it tracks, tap **Recenter**.
5. You should see numbers changing in the console. Walking sideways changes x, turning changes yaw, looking up changes pitch.

## 3. Hook up opentrack and ETS2

1. Close `udp_check.py`. Open opentrack.
2. Input: **UDP over network**, port 4242. Output: **freetrack 2.0 Enhanced**.
3. Start opentrack, then open ETS2 and look for head tracking in its controls settings.
4. If an axis moves the wrong way, tick **Invert** for it on opentrack's Mapping tab. Use the curves there to scale movement and limit how far the camera can move.
5. Hold the phone upright in portrait, hit **Recenter** whenever the view drifts off-centre.

## Known limits

- Head-look and small in-cab movement only. No walking out of the truck or drone/chase cameras (those need a game-side mod).
- Position drifts a little over long sessions; Recenter fixes it.
- Sign conventions for yaw and z may need inverting in opentrack.
