// Code Agents — Message List Component

import { store, type Message } from '../state';
import { MessageBubble } from './MessageBubble';
import { renderMarkdown } from '../markdown/renderer';

export class MessageList {
  private el: HTMLElement;
  private autoScroll = true;
  private lastMessageCount = 0;
  private lastStreamContent = '';

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'messages';
    this.el.id = 'messages';

    // Track scroll position to toggle auto-scroll
    this.el.addEventListener('scroll', () => {
      const { scrollTop, scrollHeight, clientHeight } = this.el;
      this.autoScroll = scrollHeight - scrollTop - clientHeight < 60;
    });

    store.subscribe((state) => this.onStateChange(state));
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  private onStateChange(state: ReturnType<typeof store.getState>): void {
    const messages = state.messages;

    if (messages.length !== this.lastMessageCount) {
      // New message added — only append the new ones instead of full re-render
      if (messages.length > this.lastMessageCount && this.lastMessageCount > 0) {
        for (let i = this.lastMessageCount; i < messages.length; i++) {
          const bubble = new MessageBubble(messages[i]);
          this.el.appendChild(bubble.getElement());
        }
      } else {
        // Full re-render on clear or initial load
        this.renderMessages(messages);
      }
      this.lastMessageCount = messages.length;
      this.lastStreamContent = '';
    } else if (state.isStreaming && messages.length > 0) {
      // During streaming, update only the content div of the last message
      // Avoid re-creating the entire bubble on every token
      const newContent = state.streamingContent;
      if (newContent !== this.lastStreamContent) {
        const lastChild = this.el.lastElementChild;
        if (lastChild) {
          const contentEl = lastChild.querySelector('.message-content');
          if (contentEl) {
            contentEl.innerHTML = renderMarkdown(newContent);
          } else {
            // Fallback: replace the whole bubble
            const bubble = new MessageBubble(messages[messages.length - 1]);
            lastChild.replaceWith(bubble.getElement());
          }
        }
        this.lastStreamContent = newContent;
      }
    }

    if (this.autoScroll) {
      this.scrollToBottom();
    }
  }

  private renderMessages(messages: Message[]): void {
    this.el.innerHTML = '';
    for (const msg of messages) {
      const bubble = new MessageBubble(msg);
      this.el.appendChild(bubble.getElement());
    }
  }

  scrollToBottom(): void {
    requestAnimationFrame(() => {
      this.el.scrollTop = this.el.scrollHeight;
    });
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
