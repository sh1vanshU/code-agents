package com.codeagents.plugin.ui

import com.codeagents.plugin.services.PluginSettings
import com.google.gson.Gson
import com.google.gson.JsonParser
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.ui.jcef.JBCefBrowser
import com.intellij.ui.jcef.JBCefBrowserBase
import com.intellij.ui.jcef.JBCefJSQuery
import org.cef.browser.CefBrowser
import org.cef.browser.CefFrame
import org.cef.handler.CefLoadHandlerAdapter
import java.net.URLEncoder
import java.nio.charset.StandardCharsets

class JcefBridge(private val project: Project, private val browser: JBCefBrowser) : Disposable {

    private val gson = Gson()
    private val sendQuery = JBCefJSQuery.create(browser as JBCefBrowserBase)
    private var installed = false
    private val log = com.intellij.openapi.diagnostic.Logger.getInstance(JcefBridge::class.java)

    fun install() {
        if (installed) return
        installed = true
        log.info("Installing JCEF bridge for project: ${project.name}")

        // JS -> Kotlin: handle messages from webview
        sendQuery.addHandler { message ->
            try {
                val json = JsonParser.parseString(message).asJsonObject
                handleWebviewMessage(json)
            } catch (e: Exception) {
                // Log but don't crash
                com.intellij.openapi.diagnostic.Logger.getInstance(JcefBridge::class.java)
                    .warn("Failed to handle webview message", e)
            }
            JBCefJSQuery.Response("ok")
        }

        // After page loads, inject the bridge object (guard prevents duplicate init on reload)
        browser.jbCefClient.addLoadHandler(object : CefLoadHandlerAdapter() {
            override fun onLoadEnd(cefBrowser: CefBrowser, frame: CefFrame, httpStatusCode: Int) {
                val js = """
                    if (window.ideBridge) { /* Already initialized */ } else {
                    window.ideBridge = {
                        send: function(msg) {
                            ${sendQuery.inject("msg")}
                        }
                    };
                    window._ideCallback = null;

                    // Create the unified IDE API
                    window.IDE = {
                        postMessage: function(msg) { window.ideBridge.send(JSON.stringify(msg)); },
                        onMessage: function(cb) { window._ideCallback = cb; },
                        getState: function() {
                            try { return JSON.parse(localStorage.getItem('ca-state') || '{}'); }
                            catch(e) { return {}; }
                        },
                        setState: function(s) {
                            try { localStorage.setItem('ca-state', JSON.stringify(s)); }
                            catch(e) {}
                        },
                        platform: 'intellij'
                    };

                    // Signal that bridge is ready
                    window.dispatchEvent(new Event('ideBridgeReady'));
                    } // end of if-else guard
                """.trimIndent()
                cefBrowser.executeJavaScript(js, cefBrowser.url, 0)

                // Send initial settings
                val settings = PluginSettings.getInstance()
                postMessage(mapOf(
                    "type" to "restoreState",
                    "state" to mapOf(
                        "serverUrl" to settings.serverUrl,
                        "currentAgent" to settings.defaultAgent,
                        "settings" to mapOf(
                            "theme" to settings.theme,
                            "autoRun" to settings.autoRun,
                            "requireConfirm" to settings.requireConfirm,
                            "contextWindow" to settings.state.contextWindow,
                        )
                    )
                ))
            }
        }, browser.cefBrowser)
    }

    /** Kotlin -> JS: push a message to the webview using Base64-encoded JSON to prevent injection */
    fun postMessage(msg: Map<String, Any?>) {
        val json = gson.toJson(msg)
        // Base64 encoding is injection-proof — no special chars can break out of JS string
        val encoded = java.util.Base64.getEncoder().encodeToString(json.toByteArray(StandardCharsets.UTF_8))
        browser.cefBrowser.executeJavaScript(
            "window._ideCallback && window._ideCallback(JSON.parse(atob('$encoded')));",
            browser.cefBrowser.url, 0
        )
    }

    /** Inject context from editor actions into the chat */
    fun injectContext(agent: String, message: String, filePath: String? = null) {
        postMessage(mapOf(
            "type" to "injectContext",
            "text" to message,
            "filePath" to filePath,
            "agent" to agent,
        ))
    }

    private fun handleWebviewMessage(json: com.google.gson.JsonObject) {
        val type = json.get("type")?.asString ?: return
        log.debug("Webview message: $type")

        when (type) {
            "sendMessage" -> {
                // Chat messages are sent directly from the webview via fetch() to localhost
                // No Kotlin-side handling needed for JCEF (browser has full network access)
            }

            "openFile" -> {
                val path = json.get("filePath")?.asString ?: return
                ApplicationManager.getApplication().invokeLater {
                    openFileInEditor(path)
                }
            }

            "saveSettings" -> {
                // Mutate settings on EDT to prevent thread-safety issues
                ApplicationManager.getApplication().invokeLater {
                    val settings = PluginSettings.getInstance()
                    json.getAsJsonObject("settings")?.let { s ->
                        val state = settings.state
                        s.get("serverUrl")?.asString?.let { state.serverUrl = it }
                        s.get("theme")?.asString?.let { state.theme = it }
                        s.get("autoRun")?.asBoolean?.let { state.autoRun = it }
                        s.get("requireConfirm")?.asBoolean?.let { state.requireConfirm = it }
                        s.get("contextWindow")?.asInt?.let { state.contextWindow = it }
                    }
                }
            }

            "changeAgent" -> {
                json.get("agent")?.asString?.let { agent ->
                    PluginSettings.getInstance().state.defaultAgent = agent
                }
            }
        }
    }

    private fun openFileInEditor(path: String) {
        val basePath = project.basePath ?: return

        // Block path traversal and absolute paths (works on macOS, Linux, and Windows)
        if (path.contains("..") || java.nio.file.Paths.get(path).isAbsolute) {
            return
        }

        val fullPath = "$basePath/$path"
        val resolved = java.io.File(fullPath).canonicalPath
        if (!resolved.startsWith(java.io.File(basePath).canonicalPath)) {
            return // Path escapes project root
        }

        val vf = LocalFileSystem.getInstance().findFileByPath(resolved) ?: return
        FileEditorManager.getInstance(project).openFile(vf, true)
    }

    override fun dispose() {
        sendQuery.dispose()
    }
}
