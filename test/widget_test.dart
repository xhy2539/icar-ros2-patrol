import 'package:flutter_test/flutter_test.dart';
import 'package:icar_app/main.dart';

void main() {
  testWidgets('App launches without errors', (WidgetTester tester) async {
    await tester.pumpWidget(const ICarApp());
    expect(find.text('iCar 控制台'), findsOneWidget);
  });
}
