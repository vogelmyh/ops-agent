package com.example.opsbackend.api;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpsControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void patchConfigSucceeds() throws Exception {
        mockMvc.perform(post("/api/v1/ops/patch_config")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "service": "lts-access",
                                  "config_key": "rate-limit.method-cost",
                                  "config_value": "500"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.action").value("patch_config"));
    }

    @Test
    void rollbackDeploymentSucceeds() throws Exception {
        mockMvc.perform(post("/api/v1/ops/rollback_deployment")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "service": "bcs-agent",
                                  "target_version": "bcs-agent:9.9.8-stable"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("SUCCEEDED"))
                .andExpect(jsonPath("$.action").value("rollback_deployment"));
    }

    @Test
    void unknownActionReturns404() throws Exception {
        mockMvc.perform(post("/api/v1/ops/dataplane_rollback")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"service\": \"bcs-agent\"}"))
                .andExpect(status().isNotFound());
    }

    @Test
    void missingRequiredFieldReturns400() throws Exception {
        mockMvc.perform(post("/api/v1/ops/patch_config")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"service\": \"lts-access\"}"))
                .andExpect(status().isBadRequest());
    }
}
