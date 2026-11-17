#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 Capacitor 生成的安卓工程打补丁：权限、前台服务、屏幕常亮"""
import os
import sys

BASE = "android/app/src/main"
PKG = os.path.join(BASE, "java", "com", "tiantian", "audio")

MAIN_ACTIVITY = """package com.tiantian.audio;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 播放时保持屏幕常亮，避免息屏后音频被中断
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Android 13+ 请求通知权限，用于显示播放保活通知
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
            }
        }

        // 启动前台服务，防止应用被系统回收
        try {
            Intent svc = new Intent(this, PlaybackService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                startForegroundService(svc);
            } else {
                startService(svc);
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
"""

PLAYBACK_SERVICE = """package com.tiantian.audio;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.Service;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;

public class PlaybackService extends Service {

    private static final String CHANNEL_ID = "audio_playback";
    private static final int NOTIF_ID = 1001;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }
        builder.setContentTitle("天天音乐")
                .setContentText("音频播放服务运行中")
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setOngoing(true);
        startForeground(NOTIF_ID, builder.build());
        return START_STICKY;
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "音频播放", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) {
                nm.createNotificationChannel(ch);
            }
        }
    }
}
"""

PERMISSIONS = [
    "WAKE_LOCK",
    "FOREGROUND_SERVICE",
    "FOREGROUND_SERVICE_MEDIA_PLAYBACK",
    "POST_NOTIFICATIONS",
]


def write_file(path, content):
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("写入: %s" % path)


def patch_manifest():
    path = os.path.join(BASE, "AndroidManifest.xml")
    with open(path, "r", encoding="utf-8") as f:
        xml = f.read()

    for p in PERMISSIONS:
        name = "android.permission." + p
        if name not in xml:
            xml = xml.replace(
                "</manifest>",
                '    <uses-permission android:name="%s" />\n</manifest>' % name,
            )
            print("已添加权限: %s" % p)

    if "PlaybackService" not in xml:
        svc = (
            '        <service\n'
            '            android:name=".PlaybackService"\n'
            '            android:foregroundServiceType="mediaPlayback"\n'
            '            android:exported="false" />\n'
        )
        xml = xml.replace("</application>", svc + "    </application>")
        print("已添加前台服务声明")

    with open(path, "w", encoding="utf-8") as f:
        f.write(xml)
    print("Manifest 已更新: %s" % path)


def main():
    if not os.path.isdir(BASE):
        print("错误：找不到安卓工程目录 %s" % BASE)
        sys.exit(1)

    pkg_dir = PKG
    if not os.path.isdir(pkg_dir):
        # 有些情况包路径不同，自动查找 MainActivity
        for root, dirs, files in os.walk(os.path.join(BASE, "java")):
            if "MainActivity.java" in files:
                pkg_dir = root
                break
        else:
            print("错误：找不到 MainActivity.java 所在目录")
            sys.exit(1)

    write_file(os.path.join(pkg_dir, "MainActivity.java"), MAIN_ACTIVITY)
    write_file(os.path.join(pkg_dir, "PlaybackService.java"), PLAYBACK_SERVICE)
    patch_manifest()
    print("补丁完成")


if __name__ == "__main__":
    main()
