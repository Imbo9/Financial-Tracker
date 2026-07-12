import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

// Class component: React error boundaries have no hook equivalent.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div
          style={{
            minHeight: '100vh',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 16,
            color: 'var(--text-primary)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          <span>Qualcosa è andato storto.</span>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 16px',
              borderRadius: 8,
              border: '1px solid var(--border-strong)',
              background: 'var(--bg-elevated)',
              color: 'inherit',
              font: 'inherit',
              cursor: 'pointer',
            }}
          >
            Ricarica
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
