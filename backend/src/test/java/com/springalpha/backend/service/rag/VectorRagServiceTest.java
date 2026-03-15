package com.springalpha.backend.service.rag;

import org.junit.jupiter.api.Test;
import org.springframework.ai.vectorstore.VectorStore;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.Mockito.*;

class VectorRagServiceTest {

    @Test
    void skipsDuplicateBackgroundIngestionWhileSameFilingIsInFlight() {
        VectorStore vectorStore = mock(VectorStore.class);
        VectorRagService service = new VectorRagService(vectorStore);

        assertTrue(service.shouldStartBackgroundIngestion("AMD", "same filing body"));
        assertFalse(service.shouldStartBackgroundIngestion("AMD", "same filing body"));
    }

    @Test
    void skipsSameFilingAfterItWasAlreadyStoredInCurrentSession() {
        VectorStore vectorStore = mock(VectorStore.class);
        VectorRagService service = new VectorRagService(vectorStore);

        service.storeDocument("AMD", "same filing body");

        assertFalse(service.shouldStartBackgroundIngestion("AMD", "same filing body"));
        verify(vectorStore, times(1)).add(anyList());
    }

    @Test
    void deleteDocumentsClearsInMemoryIngestionFingerprint() {
        VectorStore vectorStore = mock(VectorStore.class);
        VectorRagService service = new VectorRagService(vectorStore);

        service.storeDocument("AMD", "same filing body");
        service.deleteDocuments("AMD");

        assertTrue(service.shouldStartBackgroundIngestion("AMD", "same filing body"));
        verify(vectorStore).delete("ticker == 'AMD'");
    }
}
