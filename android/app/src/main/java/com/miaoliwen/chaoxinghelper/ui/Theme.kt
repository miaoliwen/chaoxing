package com.miaoliwen.chaoxinghelper.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

/** 设计令牌（docs/android-ui-design.md） */
object AppColors {
    val Primary = Color(0xFF1E3A8A)
    val Secondary = Color(0xFF2563EB)
    val Background = Color(0xFFF5F7FA)
    val Surface = Color(0xFFFFFFFF)
    val OnSurface = Color(0xFF1F2937)
    val OnSurfaceVariant = Color(0xFF6B7280)
    val Outline = Color(0xFFE2E8F0)
    val Success = Color(0xFF16A34A)
    val Warning = Color(0xFFD97706)
    val Error = Color(0xFFDC2626)
    val CardBg = Color(0xFFF8FAFC)

    // 日志控制台（深底）
    val LogBg = Color(0xFF0F172A)
    val LogFg = Color(0xFFE2E8F0)
    val LogTime = Color(0xFF64748B)
    val LogSuccess = Color(0xFF4ADE80)
    val LogWarning = Color(0xFFFBBF24)
    val LogError = Color(0xFFF87171)

    // 状态点
    val StatusIdle = Color(0xFF9CA3AF)
    val StatusRun = Success
    val StatusDone = Secondary
    val StatusFailed = Error
}

private val LightScheme = lightColorScheme(
    primary = AppColors.Primary,
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDBEAFE),
    onPrimaryContainer = AppColors.Primary,
    secondary = AppColors.Secondary,
    onSecondary = Color.White,
    background = AppColors.Background,
    onBackground = AppColors.OnSurface,
    surface = AppColors.Surface,
    onSurface = AppColors.OnSurface,
    onSurfaceVariant = AppColors.OnSurfaceVariant,
    outline = AppColors.Outline,
    error = AppColors.Error,
)

@Composable
fun ChaoxingTheme(content: @Composable () -> Unit) {
    // 工具型应用固定浅色（与桌面版一致），不随系统深色切换
    MaterialTheme(colorScheme = LightScheme, content = content)
}
