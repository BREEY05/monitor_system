import 'package:material_ui/material_ui.dart';

/// PULSE 设计 token —— 与 docs/mobile-app-spec.md 11.2 节 / 概念稿一致。
/// 浅色极简：白卡 + 大留白 + 克制的蓝紫渐变，红色只给严重级。
class PulseColors {
  const PulseColors._();

  static const Color bg = Color(0xFFF4F5F7);
  static const Color bgTop = Color(0xFFF8F9FB);

  static const Color card = Color(0xFFFFFFFF);
  static const Color card2 = Color(0xFFF8F9FB);

  static const Color ink = Color(0xFF0B1220);
  static const Color text = Color(0xFF101828);
  static const Color sub = Color(0xFF667085);
  static const Color dim = Color(0xFF98A2B3);
  static const Color icon = Color(0xFF475467);
  static const Color chevron = Color(0xFFC4C9D4);

  static const Color line = Color(0xFFEAECF0);
  static const Color line2 = Color(0xFFF2F4F7);

  static const Color accent = Color(0xFF3D5AFE);
  static const Color accentSoft = Color(0xFFEEF2FF);
  static const Color accentLine = Color(0xFFDDE3FF);
  static const Color accentInk = Color(0xFF2E45D9);
  static const Color accent2 = Color(0xFF8B5CF6);
  static const Color purple = Color(0xFF7C5CFF);
  static const Color purpleSoft = Color(0xFFF4F3FF);
  static const Color purpleLine = Color(0xFFE9D7FE);
  static const Color purpleInk = Color(0xFF5925DC);

  static const Color green = Color(0xFF12B76A);
  static const Color greenSoft = Color(0xFFECFDF3);
  static const Color greenLine = Color(0xFFD1FADF);
  static const Color greenInk = Color(0xFF067647);

  static const Color amber = Color(0xFFF79009);
  static const Color amberSoft = Color(0xFFFFFAEB);
  static const Color amberLine = Color(0xFFFEDF89);
  static const Color amberInk = Color(0xFFB54708);

  static const Color red = Color(0xFFF04438);
  static const Color redSoft = Color(0xFFFEF3F2);
  static const Color redLine = Color(0xFFFEE4E2);
  static const Color redInk = Color(0xFFB42318);

  static const Color segmentBg = Color(0xFFECEEF2);
  static const Color insightCard = Color(0xFFF6F8FF);
  static const Color insightLine = Color(0xFFE6EAFF);
  static const Color criticalCard = Color(0xFFFFFCFC);
}

/// 圆角：按钮/卡片/大卡/弹层。概念稿里卡片 16–22，主卡 24。
class PulseRadius {
  const PulseRadius._();

  static const double chip = 999;
  static const double tiny = 5;
  static const double small = 8;
  static const double iconButton = 12;
  static const double field = 12;
  static const double segment = 12;
  static const double tile = 18;
  static const double card = 18;
  static const double large = 20;
  static const double hero = 24;
  static const double dock = 24;
  static const double sheet = 26;
}

/// 阴影：极轻，只做层次不抢视觉。
class PulseShadow {
  const PulseShadow._();

  static const List<BoxShadow> card = <BoxShadow>[
    BoxShadow(color: Color(0x0A101828), blurRadius: 2, offset: Offset(0, 1)),
  ];

  static const List<BoxShadow> iconButton = <BoxShadow>[
    BoxShadow(color: Color(0x0A101828), blurRadius: 2, offset: Offset(0, 1)),
  ];

  static const List<BoxShadow> dock = <BoxShadow>[
    BoxShadow(color: Color(0x21101828), blurRadius: 32, offset: Offset(0, 12)),
  ];

  static const List<BoxShadow> orb = <BoxShadow>[
    BoxShadow(color: Color(0x4D3D5AFE), blurRadius: 22, offset: Offset(0, 10)),
  ];

  static const List<BoxShadow> avatar = <BoxShadow>[
    BoxShadow(color: Color(0x383D5AFE), blurRadius: 16, offset: Offset(0, 6)),
  ];

  static const List<BoxShadow> sheet = <BoxShadow>[
    BoxShadow(color: Color(0x1A101828), blurRadius: 44, offset: Offset(0, -14)),
  ];

  static const List<BoxShadow> primaryButton = <BoxShadow>[
    BoxShadow(color: Color(0x33101828), blurRadius: 20, offset: Offset(0, 8)),
  ];
}

/// 文字：系统默认无衬线（不打包字体），数字一律等宽。
class PulseText {
  const PulseText._();

  static const List<FontFeature> tabular = <FontFeature>[
    FontFeature.tabularFigures()
  ];

  static const TextStyle pageTitle = TextStyle(
    fontSize: 22,
    fontWeight: FontWeight.w700,
    height: 1.2,
    letterSpacing: -0.2,
    color: PulseColors.ink,
  );

  static const TextStyle hello = TextStyle(
    fontSize: 21,
    fontWeight: FontWeight.w700,
    height: 1.2,
    letterSpacing: -0.2,
    color: PulseColors.ink,
  );

  static const TextStyle loc = TextStyle(
    fontSize: 11,
    height: 1.4,
    letterSpacing: 0.3,
    color: PulseColors.sub,
  );

  static const TextStyle cardTitle = TextStyle(
    fontSize: 13.5,
    fontWeight: FontWeight.w700,
    height: 1.3,
    letterSpacing: -0.1,
    color: PulseColors.ink,
  );

  static const TextStyle sectionTitle = TextStyle(
    fontSize: 12.5,
    fontWeight: FontWeight.w700,
    height: 1.3,
    letterSpacing: 0.2,
    color: PulseColors.ink,
  );

  static const TextStyle sectionLink = TextStyle(
    fontSize: 10,
    height: 1.3,
    letterSpacing: 0.3,
    color: PulseColors.dim,
  );

  static const TextStyle label = TextStyle(
    fontSize: 10,
    height: 1.4,
    letterSpacing: 0.6,
    color: PulseColors.sub,
  );

  static const TextStyle labelDim = TextStyle(
    fontSize: 9.5,
    height: 1.4,
    letterSpacing: 0.4,
    color: PulseColors.dim,
  );

  static const TextStyle body = TextStyle(
    fontSize: 12,
    height: 1.56,
    color: PulseColors.text,
  );

  static const TextStyle bodySub = TextStyle(
    fontSize: 10.5,
    height: 1.5,
    color: PulseColors.sub,
  );

  static const TextStyle bodySmall = TextStyle(
    fontSize: 10.5,
    height: 1.5,
    color: Color(0xFF344054),
  );

  static const TextStyle meta = TextStyle(
    fontSize: 9.5,
    height: 1.4,
    color: PulseColors.dim,
  );

  static const TextStyle chip = TextStyle(
    fontSize: 10.5,
    height: 1.2,
    letterSpacing: 0.2,
    color: PulseColors.sub,
  );

  static const TextStyle listTitle = TextStyle(
    fontSize: 11.5,
    height: 1.3,
    letterSpacing: 0.1,
    color: PulseColors.text,
  );

  static const TextStyle listValue = TextStyle(
    fontSize: 9,
    height: 1.3,
    letterSpacing: 0.1,
    color: PulseColors.dim,
    fontFeatures: tabular,
  );

  static const TextStyle score = TextStyle(
    fontSize: 44,
    fontWeight: FontWeight.w700,
    height: 1,
    letterSpacing: -0.8,
    color: PulseColors.ink,
    fontFeatures: tabular,
  );

  static const TextStyle scoreUnit = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w500,
    height: 1,
    color: PulseColors.sub,
  );

  static const TextStyle metricValue = TextStyle(
    fontSize: 24,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: -0.2,
    color: PulseColors.ink,
    fontFeatures: tabular,
  );

  static const TextStyle metricUnit = TextStyle(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    height: 1.1,
    color: PulseColors.sub,
  );

  static const TextStyle miniValue = TextStyle(
    fontSize: 15,
    fontWeight: FontWeight.w700,
    height: 1.1,
    color: PulseColors.ink,
    fontFeatures: tabular,
  );

  static const TextStyle sheetValue = TextStyle(
    fontSize: 19,
    fontWeight: FontWeight.w700,
    height: 1.1,
    letterSpacing: -0.3,
    color: PulseColors.ink,
    fontFeatures: tabular,
  );

  static const TextStyle tinyValue = TextStyle(
    fontSize: 10,
    fontWeight: FontWeight.w600,
    height: 1.2,
    color: PulseColors.ink,
    fontFeatures: tabular,
  );

  static const TextStyle tag = TextStyle(
    fontSize: 10,
    fontWeight: FontWeight.w600,
    height: 1.2,
    letterSpacing: 0.6,
  );

  static const TextStyle button = TextStyle(
    fontSize: 10,
    fontWeight: FontWeight.w600,
    height: 1.2,
  );
}

/// 页面渐变与主题入口。
class PulseTheme {
  const PulseTheme._();

  static const LinearGradient pageGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: <Color>[PulseColors.bgTop, Color(0xFFF5F6F9), PulseColors.bg],
    stops: <double>[0, 0.32, 1],
  );

  static const LinearGradient accentGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: <Color>[Color(0xFF4F6BFF), PulseColors.accent, PulseColors.accent2],
    stops: <double>[0, 0.45, 1],
  );

  static const LinearGradient insightBarGradient = LinearGradient(
    begin: Alignment.topCenter,
    end: Alignment.bottomCenter,
    colors: <Color>[PulseColors.accent, PulseColors.accent2],
  );

  static const LinearGradient avatarGradient = LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: <Color>[Color(0xFF4F6BFF), PulseColors.accent2],
  );

  static LinearGradient sparkArea(Color color) {
    return LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: <Color>[
        color.withValues(alpha: 0.28),
        color.withValues(alpha: 0.0)
      ],
    );
  }

  static ThemeData light() {
    const ColorScheme scheme = ColorScheme.light(
      primary: PulseColors.accent,
      onPrimary: Colors.white,
      secondary: PulseColors.accent2,
      onSecondary: Colors.white,
      surface: PulseColors.card,
      onSurface: PulseColors.text,
      error: PulseColors.red,
      onError: Colors.white,
      outline: PulseColors.line,
    );

    return ThemeData(
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: PulseColors.bg,
      fontFamilyFallback: const <String>[
        'PingFang SC',
        'HarmonyOS Sans SC',
        'MiSans',
        'Microsoft YaHei',
        'Noto Sans CJK SC',
      ],
      splashFactory: InkRipple.splashFactory,
      appBarTheme: const AppBarTheme(
        backgroundColor: Colors.transparent,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        foregroundColor: PulseColors.ink,
        centerTitle: true,
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        backgroundColor: PulseColors.ink,
        contentTextStyle: const TextStyle(fontSize: 12, color: Colors.white),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      ),
      dividerColor: PulseColors.line,
      splashColor: PulseColors.accent.withValues(alpha: 0.06),
      highlightColor: Colors.transparent,
    );
  }
}
