import 'package:material_ui/material_ui.dart';

import 'package:pulse_mobile/data/mock_data.dart';
import 'package:pulse_mobile/theme/pulse_theme.dart';
import 'package:pulse_mobile/widgets/pulse_card.dart';

/// 「扫码接入新设备」入口卡。
class ScanCard extends StatelessWidget {
  const ScanCard({super.key, this.onTap});

  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return PulseCard(
      onTap: onTap,
      color: const Color(0xFFF7F9FF),
      borderColor: PulseColors.accentLine,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      child: Row(
        children: <Widget>[
          Container(
            width: 32,
            height: 32,
            decoration: BoxDecoration(
              color: PulseColors.accentSoft,
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: PulseColors.accentLine),
            ),
            child: const Icon(
              Icons.qr_code_scanner_rounded,
              size: 17,
              color: PulseColors.accent,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  MockData.scanTitle,
                  style: PulseText.cardTitle.copyWith(fontSize: 11),
                ),
                const SizedBox(height: 2),
                Text(
                  MockData.scanSubtitle,
                  style: PulseText.meta.copyWith(fontSize: 9),
                ),
              ],
            ),
          ),
          const Icon(
            Icons.chevron_right_rounded,
            size: 18,
            color: PulseColors.chevron,
          ),
        ],
      ),
    );
  }
}
