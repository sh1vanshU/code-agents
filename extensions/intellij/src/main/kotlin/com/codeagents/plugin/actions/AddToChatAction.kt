package com.codeagents.plugin.actions

import com.codeagents.plugin.services.PluginSettings
import com.codeagents.plugin.ui.ChatToolWindowFactory
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.wm.ToolWindowManager

class AddToChatAction : AnAction() {

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
        val languageId = file?.extension ?: ""

        val message = if (selectedText.isNotBlank())
            "```$languageId\n$selectedText\n```"
        else ""

        val toolWindow = ToolWindowManager.getInstance(project)
            .getToolWindow("Code Agents") ?: return

        toolWindow.show {
            val content = toolWindow.contentManager.contents.firstOrNull()
            val bridge = content?.getUserData(ChatToolWindowFactory.BRIDGE_KEY)
            val agent = PluginSettings.getInstance().defaultAgent
            bridge?.injectContext(agent, message, filePath)
        }
    }
}
