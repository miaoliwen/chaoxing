package com.miaoliwen.chaoxinghelper.core

import android.content.Context
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

object AppState {
    const val APP_VERSION = "1.0.0"

    enum class Status { IDLE, RUNNING, DONE, FAILED }

    data class Course(val title: String, val clazz: String, val courseId: String, val clazzId: String) {
        val key: String get() = "$courseId/$clazzId"
    }

    /** level: 0=info 1=success 2=warning 3=error */
    data class LogLine(val time: String, val text: String, val level: Int)

    var pythonReady by mutableStateOf(false)
    var status by mutableStateOf(Status.IDLE)
    var statusText by mutableStateOf("就绪")
    var startedAtMs by mutableStateOf(0L)
    var progressText by mutableStateOf("")
    /** -1 = 不确定进度（流动动画），0..100 = 真实百分比 */
    var progressPct by mutableStateOf(-1f)
    val logs = mutableStateListOf<LogLine>()
    var autoScroll by mutableStateOf(true)

    var courses = mutableStateListOf<Course>()
    val selectedKeys = mutableStateListOf<String>()
    var allCourses by mutableStateOf(false)
    var fetching by mutableStateOf(false)
    var fetchError by mutableStateOf<String?>(null)

    val running: Boolean get() = status == Status.RUNNING
    val form = FormState()

    private val timeFmt = SimpleDateFormat("HH:mm:ss", Locale.US)

    fun push(kind: String, raw: String) {
        android.util.Log.i("CxLog", "[$kind] $raw")
        if (kind == "progress") {
            progressText = raw.takeLast(110)
            val m = PCT_RE.find(raw)
            progressPct = if (m != null) m.groupValues[1].toFloat() else -1f
            return
        }
        val level = when {
            raw.contains("ERROR") || raw.contains("错误") || raw.contains("失败") -> 3
            raw.contains("WARNING") || raw.contains("警告") -> 2
            raw.contains("成功") || raw.contains("完成") || raw.contains("SUCCESS") -> 1
            else -> 0
        }
        logs.add(LogLine(timeFmt.format(Date()), raw, level))
        if (logs.size > 2000) logs.removeRange(0, logs.size - 1500)
    }

    fun start() {
        status = Status.RUNNING
        statusText = "任务运行中"
        startedAtMs = System.currentTimeMillis()
        progressText = ""
        progressPct = -1f
        logs.add(LogLine(timeFmt.format(Date()), ">>> 任务启动", 1))
    }

    fun finish(result: String) {
        val ok = result == "ok" || result == "exit:0" || result == "exit:None"
        status = if (ok) Status.DONE else Status.FAILED
        statusText = if (ok) "已结束" else "异常结束"
        startedAtMs = 0L
        logs.add(LogLine(timeFmt.format(Date()), ">>> 任务结束（$result）", if (ok) 1 else 3))
    }

    fun resetForNewRun() {
        status = Status.IDLE
        statusText = "就绪"
        progressText = ""
        progressPct = -1f
    }

    /** 组装 course_list：选中 > 手动 > all > 空 */
    fun resolveCourseList(): String {
        val ids = courses.filter { selectedKeys.contains(it.key) }.map { it.courseId }.distinct()
        if (ids.isNotEmpty()) return ids.joinToString(",")
        val manual = form.manualCourseIds.trim()
        if (manual.isNotEmpty()) return manual
        if (allCourses) return "all"
        return ""
    }

    private val PCT_RE = Regex("(\\d{1,3})%")
}

/** 表单状态 + SharedPreferences 持久化（明文存储与桌面版 config.ini 同级安全模型） */
class FormState {
    var username by mutableStateOf("")
    var password by mutableStateOf("")
    var useCookies by mutableStateOf(false)
    var manualCourseIds by mutableStateOf("")

    var speed by mutableStateOf("1.0")
    var jobs by mutableStateOf("4")
    var notopen by mutableStateOf("retry")
    var retryInterval by mutableStateOf("1.0")
    var redoEnabled by mutableStateOf(false)
    var redoTimes by mutableStateOf("3")
    var addCount by mutableStateOf(false)
    var targetCount by mutableStateOf("100")

    var provider by mutableStateOf("TikuYanxi")
    var tokens by mutableStateOf("")
    var submit by mutableStateOf(false)
    var coverRate by mutableStateOf("0.9")
    var delay by mutableStateOf("1.0")

    fun save(ctx: Context) {
        val o = JSONObject().apply {
            put("username", username); put("password", password); put("useCookies", useCookies)
            put("manualCourseIds", manualCourseIds)
            put("speed", speed); put("jobs", jobs); put("notopen", notopen); put("retryInterval", retryInterval)
            put("redoEnabled", redoEnabled); put("redoTimes", redoTimes)
            put("addCount", addCount); put("targetCount", targetCount)
            put("provider", provider); put("tokens", tokens); put("submit", submit)
            put("coverRate", coverRate); put("delay", delay)
            put("allCourses", AppState.allCourses)
        }
        ctx.getSharedPreferences("form", Context.MODE_PRIVATE)
            .edit().putString("json", o.toString()).apply()
    }

    fun load(ctx: Context) {
        runCatching {
            val s = ctx.getSharedPreferences("form", Context.MODE_PRIVATE).getString("json", null) ?: return
            val o = JSONObject(s)
            username = o.optString("username"); password = o.optString("password")
            useCookies = o.optBoolean("useCookies"); manualCourseIds = o.optString("manualCourseIds")
            speed = o.optString("speed", "1.0"); jobs = o.optString("jobs", "4")
            notopen = o.optString("notopen", "retry"); retryInterval = o.optString("retryInterval", "1.0")
            redoEnabled = o.optBoolean("redoEnabled"); redoTimes = o.optString("redoTimes", "3")
            addCount = o.optBoolean("addCount"); targetCount = o.optString("targetCount", "100")
            provider = o.optString("provider", "TikuYanxi"); tokens = o.optString("tokens")
            submit = o.optBoolean("submit"); coverRate = o.optString("coverRate", "0.9")
            delay = o.optString("delay", "1.0")
            AppState.allCourses = o.optBoolean("allCourses")
        }
    }
}
