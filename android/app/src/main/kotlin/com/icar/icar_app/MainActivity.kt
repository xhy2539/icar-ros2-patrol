package com.icar.icar_app

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import io.flutter.embedding.android.FlutterActivity

class MainActivity : FlutterActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Android 16 local-network protection uses the Nearby Devices group.
        // Direct TCP/WebSocket/MJPEG access to the car can otherwise time out.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            checkSelfPermission(Manifest.permission.NEARBY_WIFI_DEVICES) !=
                PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissions(
                arrayOf(Manifest.permission.NEARBY_WIFI_DEVICES),
                LOCAL_NETWORK_PERMISSION_REQUEST,
            )
        }
    }

    companion object {
        private const val LOCAL_NETWORK_PERMISSION_REQUEST = 1001
    }
}
