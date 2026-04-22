package com.codeagents.plugin.ui

import com.intellij.icons.AllIcons
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.StatusBar
import com.intellij.openapi.wm.StatusBarWidget
import com.intellij.openapi.wm.StatusBarWidgetFactory
import com.intellij.openapi.wm.ToolWindowManager
import com.codeagents.plugin.services.ServerMonitor
import java.awt.event.MouseEvent
import javax.swing.Icon

class StatusBarWidgetFactory : StatusBarWidgetFactory {
    override fun getId(): String = "CodeAgentsStatus"
    override fun getDisplayName(): String = "Code Agents"
    override fun isAvailable(project: Project): Boolean = true

    override fun createWidget(project: Project): StatusBarWidget {
        return CodeAgentsStatusWidget(project)
    }
}

class CodeAgentsStatusWidget(private val project: Project) :
    StatusBarWidget, StatusBarWidget.IconPresentation {

    private var statusBar: StatusBar? = null
    // Cached health status — @Volatile for cross-thread visibility (written from pool, read from EDT)
    @Volatile
    private var cachedConnected: Boolean = false
    private val monitor = ServerMonitor()

    init {
        monitor.addListener { connected ->
            cachedConnected = connected
            // updateWidget must be called on EDT
            com.intellij.openapi.application.ApplicationManager.getApplication().invokeLater {
                statusBar?.updateWidget(ID())
            }
        }
        monitor.startPolling()
    }

    override fun ID(): String = "CodeAgentsStatus"

    override fun getPresentation(): StatusBarWidget.WidgetPresentation = this

    override fun install(statusBar: StatusBar) {
        this.statusBar = statusBar
    }

    override fun getIcon(): Icon {
        return if (cachedConnected) AllIcons.General.InspectionsOK
        else AllIcons.General.Error
    }

    override fun getTooltipText(): String {
        return if (cachedConnected) "Code Agents: Connected"
        else "Code Agents: Disconnected"
    }

    override fun getClickConsumer(): com.intellij.util.Consumer<MouseEvent>? = com.intellij.util.Consumer {
        ToolWindowManager.getInstance(project)
            .getToolWindow("Code Agents")?.show()
    }

    override fun dispose() {
        monitor.dispose()
    }
}
