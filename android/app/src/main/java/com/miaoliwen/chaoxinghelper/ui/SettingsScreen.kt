package com.miaoliwen.chaoxinghelper.ui

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoliwen.chaoxinghelper.core.AppState

/** Tab 2 设置：学习参数 / 章节检测 / 学习次数 / 题库（docs/android-ui-design.md） */
@Composable
fun SettingsScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val f = AppState.form

    fun persist() = f.save(ctx)

    LazyColumn(
        modifier = modifier,
        contentPadding = PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SectionCard("播放与并发") {
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    DropdownField(
                        "视频倍速", listOf("1.0", "1.25", "1.5", "1.75", "2.0"), f.speed,
                        { f.speed = it; persist() },
                        modifier = Modifier.weight(1f),
                    )
                    LabeledField(
                        "并发章节数", f.jobs, { f.jobs = it; persist() },
                        modifier = Modifier.weight(1f),
                        keyboardType = KeyboardType.Number,
                        isError = f.jobs.toIntOrNull() == null,
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    DropdownField(
                        "章节关闭处理", listOf("retry", "continue"), f.notopen,
                        { f.notopen = it; persist() },
                        modifier = Modifier.weight(1f),
                    )
                    LabeledField(
                        "失败重试间隔（秒）", f.retryInterval, { f.retryInterval = it; persist() },
                        modifier = Modifier.weight(1f),
                        keyboardType = KeyboardType.Decimal,
                        isError = f.retryInterval.toFloatOrNull() == null,
                    )
                }
            }
        }
        item {
            SectionCard("章节检测（测验）") {
                SwitchRow("答错后自动重做", f.redoEnabled) { f.redoEnabled = it; persist() }
                LabeledField(
                    "最大重做次数", f.redoTimes, { f.redoTimes = it; persist() },
                    keyboardType = KeyboardType.Number,
                    isError = f.redoTimes.toIntOrNull() == null,
                )
            }
        }
        item {
            SectionCard("章节学习次数") {
                SwitchRow("刷完任务点后增加学习次数", f.addCount) { f.addCount = it; persist() }
                LabeledField(
                    "目标总次数", f.targetCount, { f.targetCount = it; persist() },
                    keyboardType = KeyboardType.Number,
                    isError = f.targetCount.toIntOrNull() == null,
                )
            }
        }
        item {
            SectionCard("题库") {
                DropdownField(
                    "题库 provider",
                    listOf("TikuYanxi", "TikuGo", "TikuLike", "TikuAdapter", "SiliconFlow", "TikuManual", ""),
                    f.provider,
                    { f.provider = it; persist() },
                )
                LabeledField("题库 Token（多个逗号分隔）", f.tokens, { f.tokens = it; persist() })
                SwitchRow("自动提交答案", f.submit) { f.submit = it; persist() }
                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    LabeledField(
                        "最低覆盖率", f.coverRate, { f.coverRate = it; persist() },
                        modifier = Modifier.weight(1f),
                        keyboardType = KeyboardType.Decimal,
                        isError = f.coverRate.toFloatOrNull() == null,
                    )
                    LabeledField(
                        "查询间隔（秒）", f.delay, { f.delay = it; persist() },
                        modifier = Modifier.weight(1f),
                        keyboardType = KeyboardType.Decimal,
                        isError = f.delay.toFloatOrNull() == null,
                    )
                }
                Text(
                    "提示：AI 大模型题库依赖 openai SDK，安卓版暂不可用。",
                    fontSize = 11.sp,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
