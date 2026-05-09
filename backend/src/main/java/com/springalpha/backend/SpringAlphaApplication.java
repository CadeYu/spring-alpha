package com.springalpha.backend;

import io.github.cdimascio.dotenv.Dotenv;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpringAlphaApplication {

	public static void main(String[] args) {
		loadEnv();
		
		SpringApplication.run(SpringAlphaApplication.class, args);
	}

	private static void loadEnv() {
		try {
			Dotenv dotenv = Dotenv.configure()
				.ignoreIfMissing()
				.load();
			
			dotenv.entries().forEach(entry -> 
				System.setProperty(entry.getKey(), entry.getValue())
			);
		} catch (Exception e) {
			// ignore
		}
	}

}
