package com.miaoliwen.chaoxinghelper.core

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import androidx.core.app.NotificationCompat

/** 前台服务：承载 Python 学习任务线程，保证息屏后任务不中断。 */
class StudyService : Service() {

    companion object {
        const val EXTRA_CONFIG = "config_path"
        private const val CHANNEL_ID = "study_channel"
        private const val NOTIF_ID = 1
        private val mainHandler = Handler(Looper.getMainLooper())
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val path = intent?.getStringExtra(EXTRA_CONFIG)
        if (path == null) {
            stopSelf()
            return START_NOT_STICKY
        }
        startInForeground()
        Thread {
            val result = try {
                Bridge.startTask(path)
            } catch (e: Exception) {
                "error:${e.message}"
            }
            mainHandler.post {
                AppState.finish(result)
                stopSelf()
            }
        }.start()
        return START_NOT_STICKY
    }

    private fun startInForeground() {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        val channel = NotificationChannel(
            CHANNEL_ID, "学习任务", NotificationManager.IMPORTANCE_LOW,
        ).apply { description = "任务运行期间保持通知以维持后台" }
        nm.createNotificationChannel(channel)
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("超星学习通助手")
            .setContentText("学习任务运行中，可返回桌面（勿划掉）")
            .setSmallIcon(android.R.drawable.ic_media_play)
            .setOngoing(true)
            .build()
        if (Build.VERSION.SDK_INT >= 29) {
            startForeground(NOTIF_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notification)
        }
    }
}
