package com.springalpha.backend.service.research;

import reactor.core.publisher.Mono;

public interface ResearchAgentClient {

    Mono<ResearchAgentResult> run(ResearchAgentRequest request);

    static ResearchAgentClient disabled() {
        return request -> Mono.empty();
    }
}
