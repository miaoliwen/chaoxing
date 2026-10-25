package com.miaoliwen.chaoxinghelper.ui

import android.Manifest
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCopy
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import com.miaoliwen.chaoxinghelper.core.AppState
import com.miaoliwen.chaoxinghelper.core.Bridge
import com.miaoliwen.chaoxinghelper.core.StudyService
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.Locale

/** Tab 3 运行：状态头 + 进度 + 开始/停止 + 深色日志控制台 */
@Composable
fun RunScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val clipboard = LocalClipboardManager.current
    var elapsed by remember { mutableStateOf("00:00") }
    var confirmStop by remember { mutableStateOf(false) }
    var startError by remember { mutableStateOf<String?>(null) }
    var writingConfig by remember { mutableStateOf(false) }
    var pendingPath by remember { mutableStateOf<String?>(null) }

    // 已运行时长
    LaunchedEffect(AppState.running) {
        while (AppState.running) {
            val s = (System.currentTimeMillis() - AppState.startedAtMs) / 1000
            elapsed = String.format(Locale.US, "%02d:%02d", s / 60, s % 60)
            delay(1000)
        }
        elapsed = "00:00"
    }

    fun launchService(path: String) {
        val intent = Intent(ctx, StudyService::class.java).putExtra(StudyService.EXTRA_CONFIG, path)
        ContextCompat.startForegroundService(ctx, intent)
        AppState.resetForNewRun()
        AppState.start()
    }

    val notifPermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { _ -> pendingPath?.let { launchService(it) } }

    Column(modifier = modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        SectionCard("任务状态") {
            Row(verticalAlignment = Alignment.CenterVertically) {
                val (dot, label) = when (AppState.status) {
                    AppState.Status.RUNNING -> AppColors.StatusRun to "任务运行中"
                    AppState.Status.DONE -> AppColors.StatusDone to "已结束"
                    AppState.Status.FAILED -> AppColors.StatusFailed to "异常结束"
                    else -> AppColors.StatusIdle to "就绪"
                }
                StatusDot(dot, label)
                Spacer(Modifier.weight(1f))
                Text(
                    if (AppState.running) "已运行 $elapsed" else "",
                    fontSize = 13.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (AppState.progressText.isNotEmpty()) {
                Text(
                    AppState.progressText,
                    fontSize = 12.sp,
                    fontFamily = FontFamily.Monospace,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    maxLines = 1,
                )
            }
            if (AppState.running) {
                if (AppState.progressPct >= 0) {
                    LinearProgressIndicator(
                        progress = { AppState.progressPct / 100f },
                        modifier = Modifier.fillMaxWidth().height(6.dp),
                        color = AppColors.Secondary,
                    )
                } else {
                    LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth().height(6.dp),
                        color = AppColors.Secondary,
                    )
                }
            } else {
                LinearProgressIndicator(
                    progress = { 0f },
                    modifier = Modifier.fillMaxWidth().height(6.dp),
                    color = AppColors.Secondary,
                )
            }

            startError?.let { Text(it, color = AppColors.Error, fontSize = 13.sp) }

            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Button(
                    onClick = {
                        startError = null
                        val err = validateStart()
                        if (err != null) {
                            startError = err
                            return@Button
                        }
                        AppState.form.save(ctx)
                        writingConfig = true
                        scope.launch {
                            val path = withContext(Dispatchers.IO) {
                                runCatching { Bridge.writeConfig(ctx) }.getOrElse { e ->
                                    withContext(Dispatchers.Main) {
                                        startError = "配置写入失败：${e.message}"
                                        writingConfig = false
                                    }
                                    null
                                }
                            }
                            writingConfig = false
                            if (path != null) {
                                pendingPath = path
                                if (Build.VERSION.SDK_INT >= 33) {
                                    notifPermission.launch(Manifest.permission.POST_NOTIFICATIONS)
                                } else {
                                    launchService(path)
                                }
                            }
                        }
                    },
                    modifier = Modifier.weight(1f).height(52.dp),
                    enabled = AppState.pythonReady && !AppState.running && !writingConfig,
                    shape = MaterialTheme.shapes.medium,
                    colors = ButtonDefaults.buttonColors(containerColor = AppColors.Secondary),
                ) {
                    Text(
                        when {
                            !AppState.pythonReady -> "引擎启动中…"
                            writingConfig -> "准备中…"
                            else -> "▶  开始任务"
                        },
                    )
                }

                if (AppState.running) {
                    Button(
                        onClick = { confirmStop = true },
                        modifier = Modifier.weight(1f).height(52.dp),
                        shape = MaterialTheme.shapes.medium,
                        colors = ButtonDefaults.buttonColors(containerColor = AppColors.Error),
                    ) { Text("■  停止") }
                }
            }
        }

        // ---- 日志控制台 ----
        val listState = rememberLazyListState()
        LaunchedEffect(AppState.logs.size, AppState.autoScroll) {
            if (AppState.autoScroll && AppState.logs.isNotEmpty()) {
                runCatching { listState.scrollToItem(AppState.logs.lastIndex) }
            }
        }
        Column(
            Modifier
                .weight(1f)
                .fillMaxWidth()
                .background(AppColors.LogBg, MaterialTheme.shapes.medium)
                .padding(horizontal = 10.dp, vertical = 6.dp),
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "运行日志",
                    color = AppColors.LogTime,
                    fontSize = 12.sp,
                    modifier = Modifier.weight(1f),
                )
                TextButton(onClick = {
                    clipboard.setText(
                        AnnotatedString(AppState.logs.joinToString("\n") { "${it.time} ${it.text}" }),
                    )
                }) {
                    Icon(
                        Icons.Filled.ContentCopy, contentDescription = "复制日志",
                        tint = AppColors.LogFg, modifier = Modifier.size(14.dp),
                    )
                    Text("复制", color = AppColors.LogFg, fontSize = 12.sp)
                }
                TextButton(onClick = { AppState.logs.clear() }) {
                    Icon(
                        Icons.Filled.Delete, contentDescription = "清空日志",
                        tint = AppColors.LogFg, modifier = Modifier.size(14.dp),
                    )
                    Text("清空", color = AppColors.LogFg, fontSize = 12.sp)
                }
                TextButton(onClick = { AppState.autoScroll = !AppState.autoScroll }) {
                    Text(
                        if (AppState.autoScroll) "跟随 ✓" else "跟随",
                        color = if (AppState.autoScroll) AppColors.LogSuccess else AppColors.LogTime,
                        fontSize = 12.sp,
                    )
                }
            }
            LazyColumn(state = listState, modifier = Modifier.fillMaxSize()) {
                items(AppState.logs.size) { i ->
                    val line = AppState.logs[i]
                    Row(Modifier.padding(vertical = 1.dp)) {
                        Text(
                            line.time + "  ",
                            color = AppColors.LogTime,
                            fontSize = 11.sp,
                            fontFamily = FontFamily.Monospace,
                        )
                        Text(
                            line.text,
                            color = when (line.level) {
                                3 -> AppColors.LogError
                                2 -> AppColors.LogWarning
                                1 -> AppColors.LogSuccess
                                else -> AppColors.LogFg
                            },
                            fontSize = 12.sp,
                            fontFamily = FontFamily.Monospace,
                        )
                    }
                }
            }
        }
    }

    if (confirmStop) {
        AlertDialog(
            onDismissRequest = { confirmStop = false },
            title = { Text("确认停止") },
            text = { Text("停止会立即结束程序（应用将退出），正在上报的学习进度可能丢失。") },
            confirmButton = {
                TextButton(onClick = {
                    confirmStop = false
                    android.os.Process.killProcess(android.os.Process.myPid())
                }) { Text("停止并退出", color = AppColors.Error) }
            },
            dismissButton = { TextButton(onClick = { confirmStop = false }) { Text("取消") } },
        )
    }
}

private fun validateStart(): String? {
    val f = AppState.form
    if (!f.useCookies && (f.username.isBlank() || f.password.isBlank())) {
        return "请填写手机号与密码，或开启 cookies.txt 登录"
    }
    if (AppState.resolveCourseList().isEmpty()) {
        return "请选择课程，或勾选「学习全部课程」/ 填写手动课程 ID"
    }
    val speed = f.speed.toFloatOrNull() ?: return "倍速必须是数字"
    if (speed < 1f || speed > 2f) return "倍速需在 1.0 ~ 2.0 之间"
    f.jobs.toIntOrNull() ?: return "并发章节数必须是整数"
    f.retryInterval.toFloatOrNull() ?: return "重试间隔必须是数字"
    f.redoTimes.toIntOrNull() ?: return "重做次数必须是整数"
    f.targetCount.toIntOrNull() ?: return "目标总次数必须是整数"
    f.coverRate.toFloatOrNull() ?: return "覆盖率必须是数字"
    f.delay.toFloatOrNull() ?: return "查询间隔必须是数字"
    return null
}
