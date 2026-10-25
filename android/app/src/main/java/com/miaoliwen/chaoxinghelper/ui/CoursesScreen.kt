package com.miaoliwen.chaoxinghelper.ui

import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.miaoliwen.chaoxinghelper.core.AppState
import com.miaoliwen.chaoxinghelper.core.Bridge
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Tab 1 课程：登录卡片 + 课程多选列表（docs/android-ui-design.md） */
@Composable
fun CoursesScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current
    val scope = rememberCoroutineScope()
    val f = AppState.form
    var showPassword by remember { mutableStateOf(false) }

    LazyColumn(
        modifier = modifier,
        contentPadding = androidx.compose.foundation.layout.PaddingValues(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        // ---- 登录卡片 ----
        item {
            SectionCard("登录信息") {
                TextField(
                    value = f.username,
                    onValueChange = { f.username = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("手机号") },
                    singleLine = true,
                    enabled = !f.useCookies,
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(
                        keyboardType = KeyboardType.Phone,
                    ),
                    shape = MaterialTheme.shapes.medium,
                )
                TextField(
                    value = f.password,
                    onValueChange = { f.password = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("密码") },
                    singleLine = true,
                    enabled = !f.useCookies,
                    visualTransformation = if (showPassword) VisualTransformation.None else PasswordVisualTransformation(),
                    trailingIcon = {
                        IconButton(onClick = { showPassword = !showPassword }) {
                            Icon(
                                if (showPassword) Icons.Filled.VisibilityOff else Icons.Filled.Visibility,
                                contentDescription = if (showPassword) "隐藏密码" else "显示密码",
                            )
                        }
                    },
                    shape = MaterialTheme.shapes.medium,
                )
                SwitchRow("使用 cookies.txt 登录", f.useCookies) { f.useCookies = it }
                Button(
                    onClick = {
                        AppState.fetchError = null
                        AppState.fetching = true
                        f.save(ctx)
                        scope.launch {
                            val err = withContext(Dispatchers.IO) {
                                try {
                                    val list = Bridge.fetchCourses(f.username.trim(), f.password)
                                    withContext(Dispatchers.Main) {
                                        AppState.courses.clear()
                                        AppState.courses.addAll(list)
                                        AppState.selectedKeys.clear()
                                    }
                                    null
                                } catch (e: Exception) {
                                    e.message ?: e.toString()
                                }
                            }
                            AppState.fetching = false
                            AppState.fetchError = err
                            if (err == null) {
                                AppState.push("line", ">>> 课程列表加载完成，共 ${AppState.courses.size} 条")
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    enabled = AppState.pythonReady && !AppState.fetching && !AppState.running && !f.useCookies,
                    shape = MaterialTheme.shapes.medium,
                    colors = ButtonDefaults.buttonColors(containerColor = AppColors.Secondary),
                ) {
                    when {
                        !AppState.pythonReady -> Text("Python 引擎启动中…")
                        AppState.fetching -> {
                            CircularProgressIndicator(
                                modifier = Modifier.size(18.dp),
                                color = androidx.compose.ui.graphics.Color.White,
                                strokeWidth = 2.dp,
                            )
                            Spacer(Modifier.size(8.dp))
                            Text("获取中…")
                        }
                        else -> {
                            Icon(Icons.Filled.Refresh, contentDescription = null)
                            Spacer(Modifier.size(8.dp))
                            Text("获取课程列表")
                        }
                    }
                }
                AppState.fetchError?.let {
                    Text(it, color = AppColors.Error, fontSize = 13.sp)
                }
            }
        }

        // ---- 课程卡片头 + 工具条 ----
        item {
            SectionCard("课程选择") {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(
                        onClick = {
                            AppState.selectedKeys.clear()
                            AppState.selectedKeys.addAll(AppState.courses.map { it.key })
                        },
                        enabled = AppState.courses.isNotEmpty() && !AppState.running,
                    ) { Text("全选") }
                    Spacer(Modifier.size(8.dp))
                    OutlinedButton(
                        onClick = { AppState.selectedKeys.clear() },
                        enabled = AppState.selectedKeys.isNotEmpty() && !AppState.running,
                    ) { Text("清空") }
                    Spacer(Modifier.weight(1f))
                    Text(
                        if (AppState.selectedKeys.isEmpty()) "未选择课程"
                        else "已选 ${AppState.selectedKeys.size} 门",
                        fontSize = 12.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                SwitchRow("学习全部课程", AppState.allCourses) { AppState.allCourses = it }
                LabeledField(
                    "手动课程 ID（逗号分隔，可留空）",
                    f.manualCourseIds,
                    { f.manualCourseIds = it },
                )
            }
        }

        // ---- 空态 / 加载骨架 / 课程行 ----
        if (AppState.fetching) {
            items(4) {
                Box(
                    Modifier
                        .fillMaxWidth()
                        .height(56.dp)
                        .background(AppColors.CardBg),
                )
            }
        } else if (AppState.courses.isEmpty()) {
            item {
                SectionCard("课程列表") {
                    Text(
                        "尚未加载课程：在上方登录并点「获取课程列表」，或勾选「学习全部课程」/ 手动填写课程 ID。",
                        fontSize = 13.sp,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            items(AppState.courses.size, key = { AppState.courses[it].key }) { i ->
                val course = AppState.courses[i]
                val checked = AppState.selectedKeys.contains(course.key)
                Row(
                    Modifier
                        .fillMaxWidth()
                        .clickable(enabled = !AppState.running) {
                            if (checked) AppState.selectedKeys.remove(course.key)
                            else AppState.selectedKeys.add(course.key)
                        }
                        .padding(horizontal = 8.dp, vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Column(Modifier.weight(1f)) {
                        Text(course.title.ifEmpty { "(未命名课程)" }, fontSize = 15.sp, maxLines = 2)
                        Text(
                            listOf(course.clazz, course.courseId).filter { it.isNotEmpty() }.joinToString(" · "),
                            fontSize = 11.sp,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Checkbox(
                        checked = checked,
                        onCheckedChange = { want ->
                            if (want) AppState.selectedKeys.add(course.key)
                            else AppState.selectedKeys.remove(course.key)
                        },
                        enabled = !AppState.running,
                    )
                }
            }
        }
    }
}
