package com.springalpha.backend;

import io.github.cdimascio.dotenv.Dotenv;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpringAlphaApplication {

	public static void main(String[] args) {
		// 优先加载本地 .env 文件 (如果存在)
		// 这允许开发者在本地使用 .env，而生产环境使用真实的环境变量
		loadEnv();
		
		SpringApplication.run(SpringAlphaApplication.class, args);
	}

	private static void loadEnv() {
		try {
			Dotenv dotenv = Dotenv.configure()
				.ignoreIfMissing() // 生产环境可能没有 .env，忽略错误
				.load();
			
			// 将 .env 变量注入到系统属性中，供 Spring @Value 读取
			dotenv.entries().forEach(entry -> 
				System.setProperty(entry.getKey(), entry.getValue())
			);
		} catch (Exception e) {
			// ignore
		}
	}

}
