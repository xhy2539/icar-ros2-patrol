import 'package:flutter/material.dart';

/// iCar 巡检小车控制端 - 全局主题配色
///
/// 配色方案:
/// - 浅灰   rgb(234,239,239) #EAEFEF - 背景
/// - 蓝灰   rgb(191,201,209) #BFC9D1 - 辅助/边框
/// - 深蓝   rgb(37,52,63)   #25343F - 文字/主色
/// - 橙色   rgb(255,155,81)  #FF9B51 - 强调/操作
/// - 蓝紫   rgb(75,86,148)  #4B5694 - 信息/点缀

class AppColors {
  static const Color background = Color(0xFFEAEFEF);
  static const Color blueGray = Color(0xFFBFC9D1);
  static const Color darkNavy = Color(0xFF25343F);
  static const Color orange = Color(0xFFFF9B51);
  static const Color bluePurple = Color(0xFF4B5694);

  // 衍生色
  static const Color surface = Color(0xFFFFFFFF);
  static const Color surfaceAlt = Color(0xFFF5F7F8);
  static const Color blueGrayLight = Color(0xFFD8E0E5);
  static const Color blueGrayDark = Color(0xFF9AABB8);
  static const Color orangeDark = Color(0xFFE0843A);
  static const Color orangeLight = Color(0xFFFFD9B8);
  static const Color darkNavyLight = Color(0xFF3A4D5C);
  static const Color successGreen = Color(0xFF4CAF50);
  static const Color warningOrange = Color(0xFFFF9800);
  static const Color errorRed = Color(0xFFE53935);
}

class AppTheme {
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: AppColors.background,
      colorScheme: const ColorScheme.light(
        primary: AppColors.orange,
        onPrimary: Colors.white,
        primaryContainer: AppColors.orangeLight,
        secondary: AppColors.bluePurple,
        onSecondary: Colors.white,
        secondaryContainer: Color(0xFFDDE0EE),
        surface: AppColors.surface,
        onSurface: AppColors.darkNavy,
        error: AppColors.errorRed,
        onError: Colors.white,
        outline: AppColors.blueGray,
      ),
      appBarTheme: const AppBarTheme(
        backgroundColor: AppColors.surface,
        foregroundColor: AppColors.darkNavy,
        elevation: 0,
        centerTitle: true,
        scrolledUnderElevation: 1,
        titleTextStyle: TextStyle(
          color: AppColors.darkNavy,
          fontSize: 20,
          fontWeight: FontWeight.w600,
        ),
      ),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        backgroundColor: AppColors.surface,
        selectedItemColor: AppColors.orange,
        unselectedItemColor: AppColors.blueGray,
        type: BottomNavigationBarType.fixed,
        elevation: 8,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: AppColors.surface,
        indicatorColor: AppColors.orange.withValues(alpha: 0.2),
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        elevation: 8,
      ),
      cardTheme: const CardThemeData(
        color: AppColors.surface,
        elevation: 1,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(16)),
        ),
        margin: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.orange,
          foregroundColor: Colors.white,
          elevation: 2,
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600),
        ),
      ),
      sliderTheme: SliderThemeData(
        activeTrackColor: AppColors.orange,
        inactiveTrackColor: AppColors.blueGray.withValues(alpha: 0.3),
        thumbColor: AppColors.orange,
        overlayColor: AppColors.orange.withValues(alpha: 0.2),
        valueIndicatorColor: AppColors.darkNavy,
        valueIndicatorTextStyle: const TextStyle(color: Colors.white),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: AppColors.surfaceAlt,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.blueGray),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.blueGrayLight),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: AppColors.orange, width: 2),
        ),
        labelStyle: const TextStyle(color: AppColors.blueGrayDark),
        hintStyle: TextStyle(color: AppColors.blueGray.withValues(alpha: 0.6)),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 14,
        ),
      ),
      dividerTheme: DividerThemeData(
        color: AppColors.blueGray.withValues(alpha: 0.3),
        thickness: 1,
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return AppColors.orange;
          }
          return AppColors.blueGray;
        }),
        trackColor: WidgetStateProperty.resolveWith((states) {
          if (states.contains(WidgetState.selected)) {
            return AppColors.orange.withValues(alpha: 0.4);
          }
          return AppColors.blueGray.withValues(alpha: 0.3);
        }),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
    );
  }
}

/// 通用卡片容器
class AppCard extends StatelessWidget {
  final Widget child;
  final String? title;
  final IconData? icon;
  final EdgeInsetsGeometry? padding;

  const AppCard({
    super.key,
    required this.child,
    this.title,
    this.icon,
    this.padding,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: padding ?? const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: AppColors.blueGray.withValues(alpha: 0.2),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.04),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (title != null) ...[
            Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, color: AppColors.bluePurple, size: 20),
                  const SizedBox(width: 8),
                ],
                Text(
                  title!,
                  style: const TextStyle(
                    color: AppColors.bluePurple,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
          ],
          child,
        ],
      ),
    );
  }
}

/// 状态指示徽章
class StatusBadge extends StatelessWidget {
  final String text;
  final Color color;
  final bool pulse;

  const StatusBadge({
    super.key,
    required this.text,
    required this.color,
    this.pulse = false,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 6),
          Text(
            text,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
