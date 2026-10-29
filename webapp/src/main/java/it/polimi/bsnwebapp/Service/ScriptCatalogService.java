package it.polimi.bsnwebapp.Service;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/**
 * Service che gestisce il catalogo degli script Python.
 * Legge i file .py dalla cartella configurata, li ordina e impedisce duplicati.
 * Consente upload da interfaccia admin con controlli su estensione e nome.
 */

@Service
public class ScriptCatalogService {

    @Value("${app.python.scripts.folder}")
    private String scriptsFolder;

    /**
     * Elenca gli script Python disponibili nella cartella configurata.
     * Filtra solo i file .py e ordina alfabeticamente per nome.
     *
     * @return lista dei nomi file script disponibili
     */
    public List<String> listScripts() {
        Path folder = Path.of(scriptsFolder);
        if (!Files.exists(folder)) {
            return List.of();
        }
        try (Stream<Path> files = Files.list(folder)) {
            return files
                    .filter(Files::isRegularFile)
                    .map(Path::getFileName)
                    .map(Path::toString)
                    .filter(name -> name.endsWith(".py"))
                    .distinct()
                    .sorted(Comparator.naturalOrder())
                    .collect(Collectors.toList());
        } catch (IOException e) {
            return List.of();
        }
    }

    /**
     * Carica uno script Python nella cartella configurata.
     * Impedisce duplicati e accetta solo file con estensione .py.
     *
     * @param file MultipartFile da salvare su disco
     * @throws IOException se la copia su filesystem fallisce
     */
    public void uploadScript(MultipartFile file) throws IOException {
        if (file == null || file.isEmpty()) {
            throw new IllegalArgumentException("Seleziona un file valido");
        }
        String originalName = file.getOriginalFilename();
        if (originalName == null || originalName.isBlank()) {
            throw new IllegalArgumentException("Nome file non valido");
        }
        String fileName = Path.of(originalName).getFileName().toString();
        if (!fileName.endsWith(".py")) {
            throw new IllegalArgumentException("Sono ammessi solo file .py");
        }

        Path folder = Path.of(scriptsFolder);
        Files.createDirectories(folder);

        Path destination = folder.resolve(fileName);
        if (Files.exists(destination)) {
            throw new IllegalStateException("Script già esistente");
        }

        Files.copy(file.getInputStream(), destination, StandardCopyOption.REPLACE_EXISTING);
    }
}
