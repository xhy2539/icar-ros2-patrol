import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';

/// Minimal MJPEG client for the car's multipart HTTP stream.
///
/// Flutter's standard NetworkImage expects one finite image response. The car
/// keeps `/video_feed` open and sends JPEG frames continuously, so we split
/// the stream at JPEG SOI/EOI markers and render the newest complete frame.
class MjpegStreamView extends StatefulWidget {
  const MjpegStreamView({
    super.key,
    required this.url,
    this.fit = BoxFit.cover,
    this.placeholder,
    this.errorBuilder,
    this.onFirstFrame,
  });

  final String url;
  final BoxFit fit;
  final Widget? placeholder;
  final Widget Function(Object error)? errorBuilder;
  final VoidCallback? onFirstFrame;

  @override
  State<MjpegStreamView> createState() => _MjpegStreamViewState();
}

class _MjpegStreamViewState extends State<MjpegStreamView> {
  static const int _maxBufferBytes = 4 * 1024 * 1024;

  HttpClient? _client;
  Uint8List? _frame;
  Object? _error;
  int _generation = 0;
  bool _reportedFirstFrame = false;

  @override
  void initState() {
    super.initState();
    _restart();
  }

  @override
  void didUpdateWidget(covariant MjpegStreamView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.url != widget.url) {
      _frame = null;
      _error = null;
      _reportedFirstFrame = false;
      _restart();
    }
  }

  void _restart() {
    _generation++;
    _client?.close(force: true);
    _client = null;
    unawaited(_readLoop(_generation));
  }

  Future<void> _readLoop(int generation) async {
    while (mounted && generation == _generation) {
      final buffer = <int>[];
      try {
        final client = HttpClient()
          ..connectionTimeout = const Duration(seconds: 5);
        _client = client;
        final request = await client.getUrl(Uri.parse(widget.url));
        request.headers.set(
          HttpHeaders.acceptHeader,
          'multipart/x-mixed-replace,image/jpeg',
        );
        final response = await request.close();
        if (response.statusCode != HttpStatus.ok) {
          throw HttpException(
            '视频服务返回 HTTP ${response.statusCode}',
            uri: Uri.parse(widget.url),
          );
        }

        await for (final chunk in response) {
          if (!mounted || generation != _generation) return;
          buffer.addAll(chunk);
          _extractFrames(buffer);
          if (buffer.length > _maxBufferBytes) {
            final start = _findMarker(buffer, 0xff, 0xd8);
            if (start > 0) {
              buffer.removeRange(0, start);
            } else if (start < 0) {
              buffer.clear();
            }
          }
        }
        client.close(force: true);
      } catch (error) {
        if (!mounted || generation != _generation) return;
        if (_frame == null) {
          setState(() => _error = error);
        }
      } finally {
        _client?.close(force: true);
        _client = null;
      }

      if (mounted && generation == _generation) {
        await Future<void>.delayed(const Duration(seconds: 1));
      }
    }
  }

  void _extractFrames(List<int> buffer) {
    while (true) {
      final start = _findMarker(buffer, 0xff, 0xd8);
      if (start < 0) return;
      final end = _findMarker(buffer, 0xff, 0xd9, start + 2);
      if (end < 0) {
        if (start > 0) buffer.removeRange(0, start);
        return;
      }

      final bytes = Uint8List.fromList(buffer.sublist(start, end + 2));
      buffer.removeRange(0, end + 2);
      if (!mounted) return;
      setState(() {
        _frame = bytes;
        _error = null;
      });
      if (!_reportedFirstFrame) {
        _reportedFirstFrame = true;
        widget.onFirstFrame?.call();
      }
    }
  }

  int _findMarker(List<int> data, int first, int second, [int from = 0]) {
    for (var i = from; i + 1 < data.length; i++) {
      if (data[i] == first && data[i + 1] == second) return i;
    }
    return -1;
  }

  @override
  void dispose() {
    _generation++;
    _client?.close(force: true);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final frame = _frame;
    if (frame != null) {
      return Image.memory(frame, fit: widget.fit, gaplessPlayback: true);
    }
    if (_error != null && widget.errorBuilder != null) {
      return widget.errorBuilder!(_error!);
    }
    return widget.placeholder ??
        const Center(child: CircularProgressIndicator());
  }
}
