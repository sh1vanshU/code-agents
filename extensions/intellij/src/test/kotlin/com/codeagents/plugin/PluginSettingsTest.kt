package com.codeagents.plugin

import com.codeagents.plugin.services.PluginSettings
import org.junit.Assert.*
import org.junit.Test

class PluginSettingsTest {

    @Test
    fun `default settings have correct values`() {
        val state = PluginSettings.SettingsState()
        assertEquals("http://localhost:8000", state.serverUrl)
        assertEquals("auto-pilot", state.defaultAgent)
        assertEquals("auto", state.theme)
        assertTrue(state.autoRun)
        assertTrue(state.requireConfirm)
        assertFalse(state.autoStartServer)
        assertEquals(5, state.contextWindow)
        assertEquals(15000L, state.statusPollingInterval)
    }

    @Test
    fun `settings state is mutable`() {
        val state = PluginSettings.SettingsState()
        state.serverUrl = "http://remote:9000"
        state.defaultAgent = "code-reviewer"
        state.theme = "dark"
        state.autoRun = false
        state.contextWindow = 10

        assertEquals("http://remote:9000", state.serverUrl)
        assertEquals("code-reviewer", state.defaultAgent)
        assertEquals("dark", state.theme)
        assertFalse(state.autoRun)
        assertEquals(10, state.contextWindow)
    }

    @Test
    fun `path traversal validation`() {
        // Mirrors the validation in JcefBridge.kt openFileInEditor
        fun isPathSafe(path: String): Boolean {
            if (path.startsWith("/") || path.startsWith("\\") || path.contains("..")) {
                return false
            }
            return true
        }

        assertFalse(isPathSafe("../../etc/passwd"))
        assertFalse(isPathSafe("/etc/shadow"))
        assertFalse(isPathSafe("\\windows\\system32"))
        assertFalse(isPathSafe("src/../../../etc/passwd"))
        assertTrue(isPathSafe("src/main.kt"))
        assertTrue(isPathSafe("build.gradle.kts"))
        assertTrue(isPathSafe("src/test/resources/data.json"))
    }
}
