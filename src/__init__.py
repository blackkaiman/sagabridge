# src/__init__.py
"""
Pachetul `src` al aplicatiei Invoice AI Extractor.

Contine modulele functionale:
    - config: configurare si variabile de mediu;
    - pdf_processor: procesare PDF locala (text + conversie imagini);
    - openai_extractor: extragere inteligenta cu OpenAI (text + Vision);
    - schema: definitii Pydantic pentru datele facturii;
    - xml_generator: generare XML deterministica;
    - validators: validatori pentru date si XML;
    - utils: functii utilitare.
"""

__version__ = "1.0.0"
__author__ = "Proiect disertatie UPB"
