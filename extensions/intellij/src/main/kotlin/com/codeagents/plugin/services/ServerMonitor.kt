package com.codeagents.plugin.services

import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.util.Alarm
import java.util.concurrent.CopyOnWriteArrayList

class ServerMonitor : Disposable {

    private val alarm = Alarm(Alarm.ThreadToUse.POOLED_THREAD, this)
    private val listeners = CopyOnWriteArrayList<(Boolean) -> Unit>()

    @Volatile
    var isConnected: Boolean = false
        private set

    fun startPolling() {
        check()
    }

    fun addListener(listener: (Boolean) -> Unit) {
        listeners.add(listener)
    }

    private fun check() {
        val settings = PluginSettings.getInstance()
        val connected = try {
            val url = java.net.URL("${settings.serverUrl}/health")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 3000
            conn.readTimeout = 3000
            conn.requestMethod = "GET"
            val ok = conn.responseCode == 200
            conn.disconnect()
            ok
        } catch (_: Exception) {
            false
        }

        if (connected != isConnected) {
            isConnected = connected
            ApplicationManager.getApplication().invokeLater {
                for (listener in listeners) {
                    listener(connected)
                }
            }
        }

        // Schedule next check
        if (!alarm.isDisposed) {
            alarm.addRequest(::check, settings.statusPollingInterval)
        }
    }

    override fun dispose() {
        alarm.dispose()
        listeners.clear()
    }
}
