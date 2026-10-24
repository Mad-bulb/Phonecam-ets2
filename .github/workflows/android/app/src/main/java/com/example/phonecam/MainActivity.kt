package com.example.phonecam

import android.Manifest
import android.content.pm.PackageManager
import android.opengl.GLES11Ext
import android.opengl.GLES20
import android.opengl.GLSurfaceView
import android.os.Bundle
import android.view.Surface
import android.view.WindowManager
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.TrackingState
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.ByteBuffer
import java.nio.ByteOrder
import javax.microedition.khronos.egl.EGLConfig
import javax.microedition.khronos.opengles.GL10
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

/**
 * Streams the phone's ARCore pose to the PhoneCam Hub on the PC (UDP port 4243).
 * Packet = 6 little-endian doubles: X, Y, Z (cm), Yaw, Pitch, Roll (degrees).
 * Hold the phone upright in portrait, like you're filming.
 */
class MainActivity : AppCompatActivity(), GLSurfaceView.Renderer {

    private val port = 4243 // PhoneCam Hub listens here and forwards to opentrack

    private var session: Session? = null
    private var installRequested = false
    private lateinit var glView: GLSurfaceView
    private lateinit var status: TextView
    private lateinit var ipField: EditText

    @Volatile private var socket: DatagramSocket? = null
    @Volatile private var target: InetAddress? = null
    @Volatile private var sending = false
    @Volatile private var recenter = true

    private var texId = 0
    private var refYaw = 0.0
    private var refX = 0.0
    private var refY = 0.0
    private var refZ = 0.0
    private var lastUi = 0L
    private val buf: ByteBuffer = ByteBuffer.allocate(48).order(ByteOrder.LITTLE_ENDIAN)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)

        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(pad, pad, pad, pad)
        }
        ipField = EditText(this).apply {
            hint = "PC IP address, e.g. 192.168.1.20"
            setText(getPreferences(MODE_PRIVATE).getString("ip", ""))
        }
        val startBtn = Button(this).apply { text = "Start sending" }
        val recenterBtn = Button(this).apply {
            text = "Recenter"
            setOnClickListener { recenter = true }
        }
        status = TextView(this).apply { text = "Idle" }

        // ARCore needs a GL surface to run, even though we draw nothing. 1px is enough.
        glView = GLSurfaceView(this).apply {
            setEGLContextClientVersion(2)
            setRenderer(this@MainActivity)
            renderMode = GLSurfaceView.RENDERMODE_CONTINUOUSLY
        }

        startBtn.setOnClickListener {
            if (sending) {
                sending = false
                socket?.close()
                socket = null
                startBtn.text = "Start sending"
                return@setOnClickListener
            }
            val ip = ipField.text.toString().trim()
            getPreferences(MODE_PRIVATE).edit().putString("ip", ip).apply()
            Thread {
                try {
                    target = InetAddress.getByName(ip)
                    socket = DatagramSocket()
                    recenter = true
                    sending = true
                    runOnUiThread { startBtn.text = "Stop sending" }
                } catch (e: Exception) {
                    runOnUiThread {
                        Toast.makeText(this, "Bad address: ${e.message}", Toast.LENGTH_LONG).show()
                    }
                }
            }.start()
        }

        val findBtn = Button(this).apply {
            text = "Find PC"
            setOnClickListener { discover() }
        }
        root.addView(ipField)
        root.addView(findBtn)
        root.addView(startBtn)
        root.addView(recenterBtn)
        root.addView(status)
        root.addView(glView, LinearLayout.LayoutParams(1, 1))
        setContentView(root)
    }

    /** Broadcasts a hello on the Wi-Fi; the PC hub answers, and we fill in its address. */
    private fun discover() {
        Thread {
            val s = DatagramSocket()
            try {
                s.broadcast = true
                s.soTimeout = 2500
                val msg = "PHONECAM_DISCOVER".toByteArray()
                s.send(DatagramPacket(msg, msg.size, InetAddress.getByName("255.255.255.255"), port))
                val reply = DatagramPacket(ByteArray(64), 64)
                s.receive(reply)
                val ip = reply.address.hostAddress ?: ""
                runOnUiThread { ipField.setText(ip) }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this, "Hub not found. Is it running? Type the PC address instead.",
                        Toast.LENGTH_LONG).show()
                }
            } finally {
                s.close()
            }
        }.start()
    }

    override fun onResume() {
        super.onResume()
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.CAMERA)
            != PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(this, arrayOf(Manifest.permission.CAMERA), 1)
            return
        }
        if (session == null) {
            try {
                if (ArCoreApk.getInstance().requestInstall(this, !installRequested)
                    == ArCoreApk.InstallStatus.INSTALL_REQUESTED
                ) {
                    installRequested = true
                    return
                }
                val s = Session(this)
                val cfg = Config(s).apply {
                    planeFindingMode = Config.PlaneFindingMode.DISABLED
                    lightEstimationMode = Config.LightEstimationMode.DISABLED
                    updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
                }
                s.configure(cfg)
                session = s
            } catch (e: Exception) {
                status.text = "ARCore error: $e"
                return
            }
        }
        try {
            session?.resume()
        } catch (e: Exception) {
            status.text = "Camera error: $e"
            return
        }
        glView.onResume()
    }

    override fun onPause() {
        super.onPause()
        glView.onPause()
        session?.pause()
    }

    override fun onDestroy() {
        sending = false
        socket?.close()
        session?.close()
        session = null
        super.onDestroy()
    }

    // ---- GL renderer: draws nothing, just pumps ARCore and sends the pose ----

    override fun onSurfaceCreated(gl: GL10?, config: EGLConfig?) {
        GLES20.glClearColor(0f, 0f, 0f, 1f)
        val t = IntArray(1)
        GLES20.glGenTextures(1, t, 0)
        texId = t[0]
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, texId)
        session?.setCameraTextureName(texId)
    }

    override fun onSurfaceChanged(gl: GL10?, width: Int, height: Int) {
        GLES20.glViewport(0, 0, width, height)
        session?.setDisplayGeometry(Surface.ROTATION_0, width, height)
    }

    override fun onDrawFrame(gl: GL10?) {
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT)
        val s = session ?: return
        try {
            s.setCameraTextureName(texId)
            val cam = s.update().camera
            if (cam.trackingState != TrackingState.TRACKING) {
                ui("Not tracking yet. Move the phone slowly and point it at textured surfaces.")
                return
            }
            val p = cam.displayOrientedPose
            val f = p.rotateVector(floatArrayOf(0f, 0f, -1f)) // where the camera points
            val u = p.rotateVector(floatArrayOf(0f, 1f, 0f))
            val r = p.rotateVector(floatArrayOf(1f, 0f, 0f))

            val yaw = Math.toDegrees(atan2(f[0].toDouble(), -f[2].toDouble()))
            val pitch = Math.toDegrees(asin(f[1].toDouble().coerceIn(-1.0, 1.0)))
            val roll = Math.toDegrees(atan2(r[1].toDouble(), u[1].toDouble()))
            val tx = p.tx().toDouble()
            val ty = p.ty().toDouble()
            val tz = p.tz().toDouble()

            if (recenter) {
                refYaw = yaw; refX = tx; refY = ty; refZ = tz
                recenter = false
            }

            var dyaw = yaw - refYaw
            while (dyaw > 180) dyaw -= 360
            while (dyaw < -180) dyaw += 360

            // Express movement relative to the heading you had when you hit Recenter.
            val yr = Math.toRadians(refYaw)
            val dx = tx - refX
            val dz = tz - refZ
            val right = (dx * cos(yr) + dz * sin(yr)) * 100.0 // cm
            val fwd = (dx * sin(yr) - dz * cos(yr)) * 100.0   // cm
            val up = (ty - refY) * 100.0                      // cm

            val sock = socket
            val tgt = target
            if (sending && sock != null && tgt != null) {
                buf.clear()
                buf.putDouble(right).putDouble(up).putDouble(fwd)
                buf.putDouble(dyaw).putDouble(pitch).putDouble(roll)
                sock.send(DatagramPacket(buf.array(), 48, tgt, port))
            }
            ui("x=%.0f y=%.0f z=%.0f cm  yaw=%.0f pitch=%.0f roll=%.0f  %s".format(
                right, up, fwd, dyaw, pitch, roll, if (sending) "SENDING" else "(not sending)"))
        } catch (e: Exception) {
            ui("Error: $e")
        }
    }

    private fun ui(text: String) {
        val now = System.currentTimeMillis()
        if (now - lastUi > 200) {
            lastUi = now
            runOnUiThread { status.text = text }
        }
    }
}
