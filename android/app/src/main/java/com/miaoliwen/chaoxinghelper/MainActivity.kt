package com.miaoliwen.chaoxinghelper

import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.MenuBook
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.lifecycle.lifecycleScope
import com.miaoliwen.chaoxinghelper.core.AppState
import com.miaoliwen.chaoxinghelper.core.Bridge
import com.miaoliwen.chaoxinghelper.ui.ChaoxingTheme
import com.miaoliwen.chaoxinghelper.ui.CoursesScreen
import com.miaoliwen.chaoxinghelper.ui.RunScreen
import com.miaoliwen.chaoxinghelper.ui.SettingsScreen
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        AppState.form.load(this)
        // Python 运行时首次解压较慢，放 IO 线程
        lifecycleScope.launch(Dispatchers.IO) {
            runCatching { Bridge.ensureInit(applicationContext) }
                .onFailure {
                    Log.e("Chaoxing", "Python 初始化失败", it)
                    AppState.push("line", ">>> Python 引擎初始化失败: ${it.message}")
                }
        }
        setContent {
            ChaoxingTheme {
                ChaoxingApp()
            }
        }
    }
}

private data class Tab(val label: String, val icon: ImageVector)

@Composable
fun ChaoxingApp() {
    val tabs = listOf(
        Tab("课程", Icons.Filled.MenuBook),
        Tab("设置", Icons.Filled.Settings),
        Tab("运行", Icons.Filled.PlayArrow),
    )
    var current by rememberSaveable { mutableIntStateOf(0) }

    Scaffold(
        topBar = {
            Column(
                Modifier
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.primary)
                    .statusBarsPadding(),
            ) {
                Row(
                    Modifier.fillMaxWidth().height(56.dp).padding(horizontal = 16.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Text(
                        "超星学习通助手",
                        color = Color.White,
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                    )
                    Spacer(Modifier.weight(1f))
                    Text(
                        "v${AppState.APP_VERSION}",
                        color = Color(0xFFC7D2FE),
                        fontSize = 12.sp,
                    )
                }
            }
        },
        bottomBar = {
            NavigationBar {
                tabs.forEachIndexed { i, tab ->
                    NavigationBarItem(
                        selected = current == i,
                        onClick = { current = i },
                        icon = { Icon(tab.icon, contentDescription = tab.label) },
                        label = { Text(tab.label) },
                    )
                }
            }
        },
    ) { padding ->
        Box(
            Modifier
                .fillMaxSize()
                .padding(padding)
                .imePadding(),
        ) {
            when (current) {
                0 -> CoursesScreen()
                1 -> SettingsScreen()
                else -> RunScreen()
            }
        }
    }
}
