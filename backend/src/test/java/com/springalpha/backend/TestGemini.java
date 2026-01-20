package com.springalpha.backend;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class TestGemini {
    public static void main(String[] args) {
        String apiKey = "AIzaSyDJj27DJA_4rmAByJ9N-p16vEQuWdUoFk8"; // 您的 Key
        String url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key=" + apiKey;
        
        String jsonBody = """
            {
              "contents": [{
                "parts":[{
                  "text": "Hello, are you working?"
                }]
              }]
            }
            """;

        try {
            HttpClient client = HttpClient.newHttpClient();
            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(url))
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(jsonBody))
                    .build();

            System.out.println("Sending request to: " + url);
            HttpResponse<String> response = client.send(request, HttpResponse.BodyHandlers.ofString());
            
            System.out.println("Status Code: " + response.statusCode());
            System.out.println("Response Body: " + response.body());
            
        } catch (Exception e) {
            e.printStackTrace();
        }
    }
}
