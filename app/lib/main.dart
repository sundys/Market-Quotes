import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'pages/home_page.dart';
import 'pages/settings_page.dart';
import 'services/api_client.dart';
import 'services/market_repository.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final repository = MarketRepository(apiClient: ApiClient(), prefs: prefs);
  runApp(MarketQuotesApp(repository: repository));
}

class MarketQuotesApp extends StatelessWidget {
  final MarketRepository repository;

  const MarketQuotesApp({super.key, required this.repository});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '行情',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      routes: {
        '/': (context) => HomePage(repository: repository),
        '/settings': (context) => const SettingsPage(),
      },
      initialRoute: '/',
    );
  }
}
