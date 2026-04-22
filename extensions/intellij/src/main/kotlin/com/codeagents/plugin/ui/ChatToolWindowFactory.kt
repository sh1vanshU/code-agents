package com.codeagents.plugin.ui

import com.codeagents.plugin.services.ServerMonitor
import com.intellij.openapi.Disposable
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.content.ContentFactory
import com.intellij.ui.jcef.JBCefApp
import com.intellij.ui.jcef.JBCefBrowser
import javax.swing.JLabel
import javax.swing.JPanel
import javax.swing.SwingConstants
import java.awt.BorderLayout

class ChatToolWindowFactory : ToolWindowFactory, DumbAware {

    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        if (JBCefApp.isSupported()) {
            createJcefContent(project, toolWindow)
        } else {
            createFallbackContent(toolWindow)
        }
    }

    private fun createJcefContent(project: Project, toolWindow: ToolWindow) {
        val browser: JBCefBrowser
        try {
            browser = JBCefBrowser()
        } catch (e: Exception) {
            com.intellij.openapi.diagnostic.Logger.getInstance(ChatToolWindowFactory::class.java)
                .warn("JCEF initialization failed, using fallback", e)
            createFallbackContent(toolWindow)
            return
        }

        // Load the bundled webview HTML
        val htmlUrl = javaClass.getResource("/webview/index.html")
        if (htmlUrl != null) {
            browser.loadURL(htmlUrl.toExternalForm())
        } else {
            // If webview not bundled, show a message
            browser.loadHTML("""
                <html>
                <body style="background:#1e1e2e;color:#cdd6f4;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh">
                    <div style="text-align:center">
                        <h2>Code Agents</h2>
                        <p>Webview files not found. Run <code>npm run build</code> in <code>extensions/vscode/webview-ui/</code> and copy <code>build/</code> to <code>src/main/resources/webview/</code>.</p>
                    </div>
                </body>
                </html>
            """.trimIndent())
        }

        // Set up the Kotlin <-> JS bridge
        val bridge = JcefBridge(project, browser)
        bridge.install()

        // Set up server monitoring
        val monitor = ServerMonitor()
        monitor.addListener { connected ->
            bridge.postMessage(mapOf("type" to "serverStatus", "connected" to connected))
        }
        monitor.startPolling()

        // Create a parent disposable that cleans up bridge, monitor, and browser
        val parentDisposable = Disposer.newDisposable("CodeAgents.ChatPanel")
        Disposer.register(parentDisposable, bridge)
        Disposer.register(parentDisposable, monitor)
        Disposer.register(parentDisposable, Disposable { browser.dispose() })

        val content = ContentFactory.getInstance()
            .createContent(browser.component, "Chat", false)
        content.setDisposer(parentDisposable)

        // Store bridge reference for actions
        content.putUserData(BRIDGE_KEY, bridge)

        toolWindow.contentManager.addContent(content)
    }

    private fun createFallbackContent(toolWindow: ToolWindow) {
        val panel = JPanel(BorderLayout())
        val label = JLabel(
            "<html><center>JCEF is not supported in this environment.<br>" +
            "Please use a JetBrains IDE with built-in browser support.</center></html>",
            SwingConstants.CENTER
        )
        panel.add(label, BorderLayout.CENTER)

        val content = ContentFactory.getInstance()
            .createContent(panel, "Chat", false)
        toolWindow.contentManager.addContent(content)
    }

    override fun shouldBeAvailable(project: Project): Boolean = true

    companion object {
        val BRIDGE_KEY = com.intellij.openapi.util.Key.create<JcefBridge>("CodeAgents.Bridge")
    }
}
