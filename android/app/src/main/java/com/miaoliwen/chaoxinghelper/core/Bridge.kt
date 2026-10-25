package com.miaoliwen.chaoxinghelper.core

import android.content.Context
import com.chaquo.python.PyObject
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONArray
import java.util.function.BiConsumer

/** Chaquopy 桥接：所有 Python 调用集中在这里。 */
object Bridge {

    @Volatile
    private var module: PyObject? = null

    private val logCb = BiConsumer<String, String> { kind, text ->
        AppState.push(kind, text)
    }

    /** 首次调用较慢（解压 Python 运行时），放 IO 线程。 */
    fun ensureInit(context: Context) {
        if (module != null) return
        synchronized(this) {
            if (module != null) return
            if (!Python.isStarted()) Python.start(AndroidPlatform(context))
            val m = Python.getInstance().getModule("android_bridge")
            m.callAttr("init", context.filesDir.absolutePath, logCb)
            module = m
            AppState.pythonReady = true
        }
    }

    /** 阻塞调用：登录并拉取课程（调用方放 IO 线程）。 */
    fun fetchCourses(user: String, pass: String): List<AppState.Course> {
        val json = requireModule().callAttr("fetch_courses", user, pass).toString()
        val arr = JSONArray(json)
        return (0 until arr.length()).map { i ->
            val o = arr.getJSONObject(i)
            AppState.Course(
                title = o.optString("title"),
                clazz = o.optString("clazz"),
                courseId = o.optString("courseId"),
                clazzId = o.optString("clazzId"),
            )
        }
    }

    /** 生成 config.ini，返回绝对路径（调用方放 IO 线程）。 */
    fun writeConfig(context: Context): String {
        val f = AppState.form
        val values: Map<String, Any> = mapOf(
            "username" to f.username, "password" to f.password,
            "use_cookies" to f.useCookies,
            "course_list" to AppState.resolveCourseList(),
            "speed" to f.speed, "jobs" to f.jobs, "notopen" to f.notopen,
            "retry_interval" to f.retryInterval,
            "redo_enabled" to f.redoEnabled, "redo_times" to f.redoTimes,
            "add_count" to f.addCount, "target_count" to f.targetCount,
            "provider" to f.provider, "tokens" to f.tokens, "submit" to f.submit,
            "cover_rate" to f.coverRate, "delay" to f.delay,
        )
        return requireModule().callAttr("write_config", values, context.filesDir.absolutePath).toString()
    }

    /** 阻塞调用：运行 main.main()（前台服务线程调用）。 */
    fun startTask(configPath: String): String {
        return try {
            requireModule().callAttr("start_task", configPath).toString()
        } catch (e: com.chaquo.python.PyException) {
            "error:${e.message}"
        }
    }

    private fun requireModule(): PyObject =
        module ?: throw IllegalStateException("Python 桥接未初始化")
}
