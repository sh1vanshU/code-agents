package com.codeagents.plugin.services

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.PersistentStateComponent
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.State
import com.intellij.openapi.components.Storage

@Service(Service.Level.APP)
@State(name = "CodeAgentsSettings", storages = [Storage("CodeAgentsPlugin.xml")])
class PluginSettings : PersistentStateComponent<PluginSettings.SettingsState> {

    data class SettingsState(
        var serverUrl: String = "http://localhost:8000",
        var defaultAgent: String = "auto-pilot",
        var theme: String = "auto",
        var autoRun: Boolean = true,
        var requireConfirm: Boolean = true,
        var autoStartServer: Boolean = false,
        var contextWindow: Int = 5,
        var statusPollingInterval: Long = 15000,
    )

    @Volatile
    private var myState = SettingsState()

    override fun getState(): SettingsState = myState

    override fun loadState(state: SettingsState) {
        myState = state
    }

    val serverUrl: String get() = myState.serverUrl
    val defaultAgent: String get() = myState.defaultAgent
    val theme: String get() = myState.theme
    val autoRun: Boolean get() = myState.autoRun
    val requireConfirm: Boolean get() = myState.requireConfirm
    val autoStartServer: Boolean get() = myState.autoStartServer
    val statusPollingInterval: Long get() = myState.statusPollingInterval

    companion object {
        fun getInstance(): PluginSettings =
            ApplicationManager.getApplication().getService(PluginSettings::class.java)
    }
}
