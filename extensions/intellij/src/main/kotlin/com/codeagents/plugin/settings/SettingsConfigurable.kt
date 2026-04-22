package com.codeagents.plugin.settings

import com.codeagents.plugin.services.PluginSettings
import com.intellij.openapi.options.BoundConfigurable
import com.intellij.openapi.ui.DialogPanel
import com.intellij.ui.dsl.builder.*

class SettingsConfigurable : BoundConfigurable("Code Agents") {

    override fun createPanel(): DialogPanel = panel {
        // Get a mutable reference to the actual state (not a copy)
        val state = PluginSettings.getInstance()

        group("Connection") {
            row("Server URL:") {
                textField()
                    .bindText(
                        getter = { state.serverUrl },
                        setter = { state.state.serverUrl = it },
                    )
                    .columns(COLUMNS_MEDIUM)
                    .comment("Code Agents server URL (default: http://localhost:8000)")
            }
            row("Auto-start server:") {
                checkBox("Start server when IDE opens")
                    .bindSelected(
                        getter = { state.autoStartServer },
                        setter = { state.state.autoStartServer = it },
                    )
            }
        }

        group("Defaults") {
            row("Default agent:") {
                comboBox(listOf(
                    "auto-pilot", "code-writer", "code-reviewer", "code-reasoning",
                    "code-tester", "test-coverage", "qa-regression", "jenkins-cicd",
                    "argocd-verify", "git-ops", "jira-ops", "redash-query", "security",
                ))
                    .bindItem(
                        getter = { state.defaultAgent },
                        setter = { it?.let { v -> state.state.defaultAgent = v } },
                    )
            }
            row("Context window:") {
                spinner(1..20)
                    .bindIntValue(
                        getter = { state.state.contextWindow },
                        setter = { state.state.contextWindow = it },
                    )
                    .comment("Number of conversation pairs to keep")
            }
        }

        group("Behavior") {
            row("Auto-run commands:") {
                checkBox("Automatically execute safe commands")
                    .bindSelected(
                        getter = { state.autoRun },
                        setter = { state.state.autoRun = it },
                    )
            }
            row("Require confirmation:") {
                checkBox("Ask before executing commands")
                    .bindSelected(
                        getter = { state.requireConfirm },
                        setter = { state.state.requireConfirm = it },
                    )
            }
        }

        group("Theme") {
            row("Chat theme:") {
                comboBox(listOf("auto", "dark", "light", "high-contrast"))
                    .bindItem(
                        getter = { state.theme },
                        setter = { it?.let { v -> state.state.theme = v } },
                    )
                    .comment("Color theme for the chat panel")
            }
        }

        group("Health Check") {
            row("Polling interval:") {
                spinner(5000..60000, 1000)
                    .bindIntValue(
                        getter = { state.state.statusPollingInterval.toInt() },
                        setter = { state.state.statusPollingInterval = it.toLong() },
                    )
                    .comment("Milliseconds between health checks")
            }
        }
    }
}
