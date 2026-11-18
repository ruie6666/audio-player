#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""为 Capacitor 生成的安卓工程打补丁：
   权限、前台服务、媒体通知（下拉菜单/锁屏播放控制）、屏幕常亮
"""
import os
import sys

BASE = "android/app/src/main"
PKG = os.path.join(BASE, "java", "com", "tiantian", "audio")

MAIN_ACTIVITY = """package com.tiantian.audio;

import android.Manifest;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {

    private BroadcastReceiver mediaReceiver;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // 播放时保持屏幕常亮
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        // Android 13+ 通知权限
        if (Build.VERSION.SDK_INT >= 33) {
            if (checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)
                    != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
            }
        }

        // 启动前台服务
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

        registerMediaReceiver();
        setupWebView();
    }

    private void setupWebView() {
        if (getBridge() == null || getBridge().getWebView() == null) return;
        try {
            // 允许通知栏按钮在没有页面手势的情况下触发播放
            getBridge().getWebView().getSettings().setMediaPlaybackRequiresUserGesture(false);
        } catch (Exception e) {
            e.printStackTrace();
        }
        // 把 JS 桥暴露给网页
        getBridge().getWebView().addJavascriptInterface(new MediaBridge(), "AndroidMedia");
    }

    private void registerMediaReceiver() {
        mediaReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context context, Intent intent) {
                String cmd = intent.getStringExtra(PlaybackService.EXTRA_CMD);
                if (cmd == null) return;
                String js;
                if (PlaybackService.CMD_PLAY.equals(cmd)) {
                    js = "window.__nativePlay&&window.__nativePlay()";
                } else if (PlaybackService.CMD_PAUSE.equals(cmd)) {
                    js = "window.__nativePause&&window.__nativePause()";
                } else if (PlaybackService.CMD_NEXT.equals(cmd)) {
                    js = "window.__nativeNext&&window.__nativeNext()";
                } else if (PlaybackService.CMD_PREV.equals(cmd)) {
                    js = "window.__nativePrev&&window.__nativePrev()";
                } else if (PlaybackService.CMD_CYCLE.equals(cmd)) {
                    js = "window.__nativeCycle&&window.__nativeCycle()";
                } else if (PlaybackService.CMD_MODE_SINGLE.equals(cmd)) {
                    js = "window.__nativeSetMode&&window.__nativeSetMode('single')";
                } else if (PlaybackService.CMD_MODE_LOOP.equals(cmd)) {
                    js = "window.__nativeSetMode&&window.__nativeSetMode('loop')";
                } else {
                    return;
                }
                final String code = js;
                if (getBridge() != null && getBridge().getWebView() != null) {
                    getBridge().getWebView().post(new Runnable() {
                        @Override
                        public void run() {
                            getBridge().getWebView().evaluateJavascript(code, null);
                        }
                    });
                }
            }
        };

        IntentFilter filter = new IntentFilter(PlaybackService.ACTION_CMD);
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(mediaReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            registerReceiver(mediaReceiver, filter);
        }
    }

    @Override
    public void onDestroy() {
        if (mediaReceiver != null) {
            try {
                unregisterReceiver(mediaReceiver);
            } catch (Exception ignored) {
            }
        }
        super.onDestroy();
    }

    /** 网页调用：同步当前曲目、播放状态与循环模式到系统媒体控制 */
    public static class MediaBridge {
        @JavascriptInterface
        public void update(String title, boolean playing, String mode) {
            PlaybackService.update(title, playing, mode);
        }
    }
}
"""

PLAYBACK_SERVICE = """package com.tiantian.audio;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.media.MediaMetadata;
import android.media.session.MediaSession;
import android.media.session.PlaybackState;
import android.os.Build;
import android.os.IBinder;

public class PlaybackService extends Service {

    public static final String ACTION_CMD = "com.tiantian.audio.MEDIA_CMD";
    public static final String EXTRA_CMD = "cmd";
    public static final String CMD_PLAY = "play";
    public static final String CMD_PAUSE = "pause";
    public static final String CMD_NEXT = "next";
    public static final String CMD_PREV = "prev";
    public static final String CMD_CYCLE = "cycle";
    public static final String CMD_MODE_SINGLE = "mode_single";
    public static final String CMD_MODE_LOOP = "mode_loop";

    private static final String CHANNEL_ID = "audio_playback";
    private static final int NOTIF_ID = 1001;

    private static PlaybackService instance;

    private MediaSession mediaSession;
    private String currentTitle = "天天音乐";
    private String currentMode = "loop";
    private boolean isPlaying = false;

    @Override
    public void onCreate() {
        super.onCreate();
        instance = this;
        createChannel();
        initMediaSession();
    }

    private void initMediaSession() {
        mediaSession = new MediaSession(this, "TianTianMusic");
        mediaSession.setCallback(new MediaSession.Callback() {
            @Override
            public void onPlay() {
                sendCmd(CMD_PLAY);
            }

            @Override
            public void onPause() {
                sendCmd(CMD_PAUSE);
            }

            @Override
            public void onSkipToNext() {
                sendCmd(CMD_NEXT);
            }

            @Override
            public void onSkipToPrevious() {
                sendCmd(CMD_PREV);
            }
        });
        mediaSession.setActive(true);
    }

    private void sendCmd(String cmd) {
        Intent i = new Intent(ACTION_CMD);
        i.setPackage(getPackageName());
        i.putExtra(EXTRA_CMD, cmd);
        sendBroadcast(i);
    }

    /** 网页调用，更新通知与媒体会话 */
    public static void update(String title, boolean playing, String mode) {
        PlaybackService s = instance;
        if (s == null) return;
        if (title != null && title.length() > 0) {
            s.currentTitle = title;
        }
        if (mode != null && mode.length() > 0) {
            s.currentMode = mode;
        }
        s.isPlaying = playing;
        s.refresh();
    }

    private String modeLabel() {
        if ("single".equals(currentMode)) return "单曲循环";
        if ("shuffle".equals(currentMode)) return "随机播放";
        return "列表循环";
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String cmd = intent != null ? intent.getStringExtra(EXTRA_CMD) : null;
        if (cmd != null) {
            sendCmd(cmd);
        }
        startForeground(NOTIF_ID, buildNotification());
        return START_STICKY;
    }

    private void refresh() {
        try {
            MediaMetadata md = new MediaMetadata.Builder()
                    .putString(MediaMetadata.METADATA_KEY_TITLE, currentTitle)
                    .putString(MediaMetadata.METADATA_KEY_ARTIST, "天天音乐")
                    .putString(MediaMetadata.METADATA_KEY_ALBUM, "门店音频")
                    .build();
            mediaSession.setMetadata(md);

            int state = isPlaying ? PlaybackState.STATE_PLAYING : PlaybackState.STATE_PAUSED;
            PlaybackState ps = new PlaybackState.Builder()
                    .setActions(PlaybackState.ACTION_PLAY
                            | PlaybackState.ACTION_PAUSE
                            | PlaybackState.ACTION_PLAY_PAUSE
                            | PlaybackState.ACTION_SKIP_TO_NEXT
                            | PlaybackState.ACTION_SKIP_TO_PREVIOUS)
                    .setState(state, PlaybackState.PLAYBACK_POSITION_UNKNOWN, 1.0f)
                    .build();
            mediaSession.setPlaybackState(ps);

            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (nm != null) {
                nm.notify(NOTIF_ID, buildNotification());
            }
        } catch (Exception e) {
            e.printStackTrace();
        }
    }

    private PendingIntent commandIntent(String cmd, int requestCode) {
        Intent i = new Intent(this, PlaybackService.class);
        i.putExtra(EXTRA_CMD, cmd);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getService(this, requestCode, i, flags);
    }

    private PendingIntent contentIntent() {
        Intent i = new Intent(this, MainActivity.class);
        i.setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            flags |= PendingIntent.FLAG_IMMUTABLE;
        }
        return PendingIntent.getActivity(this, 0, i, flags);
    }

    private Notification buildNotification() {
        Notification.Builder b;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            b = new Notification.Builder(this, CHANNEL_ID);
        } else {
            b = new Notification.Builder(this);
        }

        b.setContentTitle("天天音乐")
                .setContentText(currentTitle)
                .setSubText(modeLabel())
                .setSmallIcon(android.R.drawable.ic_media_play)
                .setContentIntent(contentIntent())
                .setOngoing(isPlaying)
                .setOnlyAlertOnce(true)
                .setVisibility(Notification.VISIBILITY_PUBLIC);

        b.addAction(new Notification.Action.Builder(
                android.R.drawable.ic_media_previous, "上一首", commandIntent(CMD_PREV, 11)).build());
        b.addAction(new Notification.Action.Builder(
                isPlaying ? android.R.drawable.ic_media_pause : android.R.drawable.ic_media_play,
                isPlaying ? "暂停" : "播放",
                commandIntent(isPlaying ? CMD_PAUSE : CMD_PLAY, 12)).build());
        b.addAction(new Notification.Action.Builder(
                android.R.drawable.ic_media_next, "下一首", commandIntent(CMD_NEXT, 13)).build());
        b.addAction(new Notification.Action.Builder(
                android.R.drawable.ic_menu_rotate, modeLabel(), commandIntent(CMD_CYCLE, 14)).build());

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP && mediaSession != null) {
            b.setStyle(new Notification.MediaStyle()
                    .setMediaSession(mediaSession.getSessionToken())
                    .setShowActionsInCompactView(0, 1, 2));
        }

        return b.build();
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
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
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
