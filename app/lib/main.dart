import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'pages/home_page.dart';
import 'pages/settings_page.dart';
import 'services/api_client.dart';
import 'services/market_repository.dart';
import 'services/settings_service.dart';
import 'services/update_service.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  final settings = SettingsService(prefs);
  final repository = MarketRepository(apiClient: ApiClient(), prefs: prefs, settings: settings);
  runApp(MarketQuotesApp(
    settings: settings,
    repository: repository,
    updateService: UpdateService(),
  ));
}

class MarketQuotesApp extends StatelessWidget {
  final SettingsService settings;
  final MarketRepository repository;
  final UpdateService updateService;

  const MarketQuotesApp({
    super.key,
    required this.settings,
    required this.repository,
    required this.updateService,
  });

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '行情',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light(),
      routes: {
        '/': (context) =>
            HomePage(repository: repository, settings: settings),
        '/settings': (context) => SettingsPage(settings: settings, updateService: updateService),
      },
      initialRoute: '/',
    );
  }
}
