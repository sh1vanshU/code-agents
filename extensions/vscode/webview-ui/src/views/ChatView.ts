// Code Agents — Chat View (main composition)

import { store } from '../state';
import { Toolbar } from '../components/Toolbar';
import { MessageList } from '../components/MessageList';
import { ChatInput } from '../components/ChatInput';
import { WelcomeView } from './WelcomeView';
import { PlanTracker } from '../components/PlanTracker';
import { SlashPalette } from '../components/SlashPalette';

export class ChatView {
  private el: HTMLElement;
  private toolbar: Toolbar;
  private messageList: MessageList;
  private chatInput: ChatInput;
  private welcome: WelcomeView;
  private planTracker: PlanTracker;
  private slashPalette: SlashPalette;
  private scrollBtn: HTMLButtonElement;

  constructor() {
    this.el = document.createElement('div');
    this.el.className = 'chat-view';
    this.el.style.cssText = 'display:flex;flex-direction:column;height:100%;position:relative';

    // Create components
    this.toolbar = new Toolbar();
    this.messageList = new MessageList();
    this.chatInput = new ChatInput();
    this.welcome = new WelcomeView();
    this.planTracker = new PlanTracker();
    this.slashPalette = new SlashPalette();

    // Scroll to bottom button
    this.scrollBtn = document.createElement('button');
    this.scrollBtn.className = 'scroll-bottom hidden';
    this.scrollBtn.innerHTML = '&#8595;';
    this.scrollBtn.title = 'Scroll to bottom';
    this.scrollBtn.addEventListener('click', () => {
      this.messageList.scrollToBottom();
    });

    // Build layout
    this.toolbar.mount(this.el);

    // Messages area (relative positioned for scroll button)
    const messagesArea = document.createElement('div');
    messagesArea.style.cssText = 'flex:1;position:relative;overflow:hidden;display:flex;flex-direction:column';

    this.welcome.mount(messagesArea);
    this.messageList.mount(messagesArea);
    this.planTracker.mount(messagesArea);
    messagesArea.appendChild(this.scrollBtn);

    this.el.appendChild(messagesArea);

    // Input area (with slash palette mount)
    this.chatInput.mount(this.el);
    const slashMount = this.el.querySelector('#slash-palette-mount');
    if (slashMount) {
      this.slashPalette.mount(slashMount as HTMLElement);
    }

    // State subscriptions
    store.subscribe((state) => {
      // Show/hide welcome
      if (state.messages.length === 0 && !state.isStreaming) {
        this.welcome.show();
        this.messageList.getElement().style.display = 'none';
      } else {
        this.welcome.hide();
        this.messageList.getElement().style.display = '';
      }

      // Streaming indicator
      const msgEl = this.messageList.getElement();
      const { scrollTop, scrollHeight, clientHeight } = msgEl;
      const atBottom = scrollHeight - scrollTop - clientHeight < 60;
      this.scrollBtn.classList.toggle('hidden', atBottom || state.messages.length === 0);
    });
  }

  mount(parent: HTMLElement): void {
    parent.appendChild(this.el);
  }

  show(): void { this.el.style.display = 'flex'; }
  hide(): void { this.el.style.display = 'none'; }

  /** Focus the chat input */
  focus(): void {
    this.chatInput.focus();
  }

  /** Set text in input (for context injection) */
  setInput(text: string): void {
    this.chatInput.setText(text);
  }

  getElement(): HTMLElement {
    return this.el;
  }
}
