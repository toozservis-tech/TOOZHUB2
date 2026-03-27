import SwiftUI

@main
struct SpravaVozidelApp: App {
    @StateObject private var environment = AppEnvironment()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(environment)
                .environmentObject(environment.authManager)
                .task {
                    await environment.authManager.bootstrap()
                }
        }
    }
}
