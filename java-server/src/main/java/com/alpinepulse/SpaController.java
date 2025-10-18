package com.alpinepulse;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

/**
 * Forwards any non-file route to index.html so the SPA router can handle it.
 */
@Controller
public class SpaController {

    @GetMapping({"/", "/{path:^(?!api|static|assets|images|css|js|webjars).*$}"})
    public String index() {
        return "forward:/index.html";
    }
}

