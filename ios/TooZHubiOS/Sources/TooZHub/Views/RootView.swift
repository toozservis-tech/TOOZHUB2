import SwiftUI

struct RootView: View {
    @EnvironmentObject private var env: AppEnvironment
    @EnvironmentObject private var authManager: AuthManager

    var body: some View {
        Group {
            if authManager.isAuthenticated {
                MainTabView()
            } else {
                LoginView()
            }
        }
        .animation(.easeInOut(duration: 0.25), value: authManager.isAuthenticated)
        .safeAreaInset(edge: .top, spacing: 0) {
            if env.serverStatusMonitor.state != .online {
                HStack {
                    Spacer()
                    ServerStatusBadge(state: env.serverStatusMonitor.state)
                        .onTapGesture {
                            Task { await env.serverStatusMonitor.checkNow() }
                        }
                }
                .padding(.horizontal, 12)
                .padding(.top, authManager.isAuthenticated ? 2 : 6)
                .padding(.bottom, authManager.isAuthenticated ? 6 : 2)
            }
        }
        .overlay(alignment: .bottom) {
            if let message = env.serverStatusMonitor.userMessage {
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .foregroundStyle(.yellow)
                    Text(message)
                        .font(.caption)
                        .foregroundStyle(.white)
                        .multilineTextAlignment(.leading)
                    Spacer()
                    Button("OK") {
                        env.serverStatusMonitor.stop()
                        env.serverStatusMonitor.start()
                    }
                    .font(.caption.bold())
                    .foregroundStyle(.white)
                }
                .padding(12)
                .background(.black.opacity(0.82), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
                .padding(.horizontal, 12)
                .padding(.bottom, 16)
            }
        }
    }
}
