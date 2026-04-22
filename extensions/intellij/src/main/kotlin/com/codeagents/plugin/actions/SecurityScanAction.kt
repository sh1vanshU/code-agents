package com.codeagents.plugin.actions

class SecurityScanAction : BaseAgentAction("security") {
    override fun buildContextMessage(
        fileName: String, filePath: String, selectedText: String, languageId: String,
    ): String {
        return if (selectedText.isNotBlank())
            "Run a security audit (OWASP, CVE, secrets detection) on this code:\n\n```$languageId\n$selectedText\n```"
        else
            "Run a security audit on: $filePath"
    }
}
