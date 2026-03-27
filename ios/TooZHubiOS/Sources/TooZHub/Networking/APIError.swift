import Foundation

enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case forbidden
    case developerAppRequired
    case serverError(String)
    case decodingError
    case transportError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Neplatná URL API."
        case .unauthorized:
            return "Relace vypršela. Přihlaste se znovu."
        case .forbidden:
            return "Nemáte oprávnění pro tuto akci."
        case .developerAppRequired:
            return "Developer/Admin účet se přihlašuje v samostatné developer aplikaci."
        case .serverError(let message):
            return message
        case .decodingError:
            return "Nepodařilo se zpracovat odpověď serveru."
        case .transportError(let message):
            return message
        }
    }
}
