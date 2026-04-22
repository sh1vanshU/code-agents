package com.codeagents.plugin.actions

import com.codeagents.plugin.ui.ChatToolWindowFactory
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.wm.ToolWindowManager

abstract class BaseAgentAction(private val agentName: String) : AnAction() {

    override fun getActionUpdateThread(): ActionUpdateThread = ActionUpdateThread.EDT

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val editor = e.getData(CommonDataKeys.EDITOR)
        val file = e.getData(CommonDataKeys.VIRTUAL_FILE)

        val selectedText = editor?.selectionModel?.selectedText ?: ""
        val filePath = file?.let { vf ->
            project.basePath?.let { base ->
                vf.path.removePrefix(base).removePrefix("/")
            } ?: vf.path
        } ?: ""
        val fileName = file?.name ?: ""
        val languageId = file?.extension ?: ""

        val message = buildContextMessage(fileName, filePath, selectedText, languageId)

        // Open the tool window and inject context
        val toolWindow = ToolWindowManager.getInstance(project)
            .getToolWindow("Code Agents") ?: return

        toolWindow.show {
            val content = toolWindow.contentManager.contents.firstOrNull()
            val bridge = content?.getUserData(ChatToolWindowFactory.BRIDGE_KEY)
            if (bridge != null) {
                bridge.injectContext(agentName, message, filePath)
            } else {
                com.intellij.notification.NotificationGroupManager.getInstance()
                    .getNotificationGroup("Code Agents")
                    .createNotification("Code Agents chat not ready. Try again.", com.intellij.notification.NotificationType.WARNING)
                    .notify(project)
            }
        }
    }

    abstract fun buildContextMessage(
        fileName: String,
        filePath: String,
        selectedText: String,
        languageId: String,
    ): String
}
