import 'package:material_ui/material_ui.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';

/// 底部 dock：4 个 tab + 中央渐变 AI 光球（点击进入 AI 全屏路由）。
class PulseDock extends StatelessWidget {
  const PulseDock({
    super.key,
    required this.currentIndex,
    required this.onTabSelected,
    required this.onOrbTap,
  });

  final int currentIndex;
  final ValueChanged<int> onTabSelected;
  final VoidCallback onOrbTap;

  static const List<String> labels = <String>['总览', '设备', '报警', '我的'];
  static const List<IconData> icons = <IconData>[
    Icons.grid_view_rounded,
    Icons.memory_rounded,
    Icons.notifications_none_rounded,
    Icons.person_outline_rounded,
  ];

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 68,
      padding: const EdgeInsets.symmetric(horizontal: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.94),
        borderRadius: BorderRadius.circular(PulseRadius.dock),
        border: Border.all(color: const Color(0x0F101828), width: 1),
        boxShadow: PulseShadow.dock,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: _DockItem(
              label: labels[0],
              icon: icons[0],
              selected: currentIndex == 0,
              onTap: () => onTabSelected(0),
            ),
          ),
          Expanded(
            child: _DockItem(
              label: labels[1],
              icon: icons[1],
              selected: currentIndex == 1,
              onTap: () => onTabSelected(1),
            ),
          ),
          SizedBox(
            width: 62,
            child: Center(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: onOrbTap,
                child: Container(
                  width: 52,
                  height: 52,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: PulseTheme.accentGradient,
                    border: Border.all(color: Colors.white, width: 5),
                    boxShadow: PulseShadow.orb,
                  ),
                  child: const Icon(
                    Icons.auto_awesome_rounded,
                    color: Colors.white,
                    size: 23,
                  ),
                ),
              ),
            ),
          ),
          Expanded(
            child: _DockItem(
              label: labels[2],
              icon: icons[2],
              selected: currentIndex == 2,
              onTap: () => onTabSelected(2),
            ),
          ),
          Expanded(
            child: _DockItem(
              label: labels[3],
              icon: icons[3],
              selected: currentIndex == 3,
              onTap: () => onTabSelected(3),
            ),
          ),
        ],
      ),
    );
  }
}

class _DockItem extends StatelessWidget {
  const _DockItem({
    required this.label,
    required this.icon,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final IconData icon;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final Color color = selected ? PulseColors.ink : PulseColors.sub;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: SizedBox(
        height: 60,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(icon, size: 21, color: color),
            const SizedBox(height: 3),
            Text(
              label,
              style: TextStyle(
                fontSize: 9.5,
                height: 1.1,
                letterSpacing: 0.2,
                fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
                color: color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
