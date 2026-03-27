import Foundation

enum HTTPMethod: String {
    case get = "GET"
    case post = "POST"
    case put = "PUT"
    case delete = "DELETE"
}

struct APIEndpoint {
    let path: String
    let method: HTTPMethod
    var queryItems: [URLQueryItem] = []
    var body: Data? = nil

    static func get(_ path: String, queryItems: [URLQueryItem] = []) -> APIEndpoint {
        APIEndpoint(path: path, method: .get, queryItems: queryItems)
    }

    static func post(_ path: String, body: Data? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .post, body: body)
    }

    static func put(_ path: String, body: Data? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .put, body: body)
    }

    static func delete(_ path: String, body: Data? = nil) -> APIEndpoint {
        APIEndpoint(path: path, method: .delete, body: body)
    }
}
