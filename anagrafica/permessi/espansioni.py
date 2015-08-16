from datetime import date

__author__ = 'alfioemanuele'

from anagrafica.permessi.costanti import GESTIONE_SOCI, ELENCHI_SOCI, GESTIONE_ATTIVITA_SEDE, GESTIONE_CORSI_SEDE, \
    GESTIONE_SEDE, GESTIONE_ATTIVITA_AREA, GESTIONE_ATTIVITA, GESTIONE_CORSO, MODIFICA, LETTURA, COMPLETO

"""
Questo file gestisce la espansione dei permessi in Gaia.

 ============================================================================================
 |                                    ! HEEEEY, TU !                                        |
 ============================================================================================
  Prima di avventurarti da queste parti, assicurati di leggere la documentazione a:
   https://github.com/CroceRossaItaliana/jorvik/wiki/Deleghe,-Permessi-e-Livelli-di-Accesso
 ============================================================================================
"""


def espandi_gestione_soci(qs_sedi, al_giorno=date.today()):
    from anagrafica.models import Persona, Appartenenza
    return [
        (MODIFICA,  Persona.objects.filter(Appartenenza.query_attuale(figli=False, al_giorno=al_giorno, membro__in=Appartenenza.MEMBRO_DIRETTO).via("appartenenze"))),
        (LETTURA,   Persona.objects.filter(Appartenenza.query_attuale(figli=False, al_giorno=al_giorno, membro__in=Appartenenza.MEMBRO_ESTESO).via("appartenenze")))
    ]

def espandi_elenchi_soci(qs_sedi, al_giorno=date.today()):
    from anagrafica.models import Persona, Appartenenza
    return [
        (LETTURA,  Persona.objects.filter(Appartenenza.query_attuale(figli=True, al_giorno=al_giorno).via("appartenenze"))),
        (LETTURA,  Persona.objects.filter(Appartenenza.query_attuale(figli=False, al_giorno=al_giorno, membro__in=Appartenenza.MEMBRO_DIRETTO).via("appartenenze"))),
        (LETTURA,  Persona.objects.filter(Appartenenza.query_attuale(figli=False, al_giorno=al_giorno, membro__in=Appartenenza.MEMBRO_ESTESO).via("appartenenze"))),
    ]

def espandi_gestione_sede(qs_sedi, al_giorno=date.today()):
    from anagrafica.models import Sede
    return [
        (MODIFICA,  qs_sedi),
        (MODIFICA,  Sede.objects.get_queryset_descendants(qs_sedi, include_self=True)),
    ]

def espandi_gestione_attivita_sede(qs_sedi, al_giorno=date.today()):
    from attivita.models import Attivita
    return [
        (COMPLETO,  Attivita.objects.filter(sede__in=qs_sedi)),
    ] \
        + espandi_gestione_attivita(Attivita.objects.filter(sede__in=qs_sedi))

def espandi_gestione_attivita_area(qs_aree, al_giorno=date.today()):
    from attivita.models import Attivita
    return [
        (COMPLETO,  Attivita.objects.filter(area__in=qs_aree)),
    ] \
        + espandi_gestione_attivita(Attivita.objects.filter(area__in=qs_aree))

def espandi_gestione_attivita(qs_attivita, al_giorno=date.today()):
    from anagrafica.models import Persona
    return [
        (MODIFICA,  qs_attivita),
        (LETTURA,   Persona.objects.filter(partecipazioni__turno__attivita__in=qs_attivita))
    ]

def espandi_gestione_corsi_sede(qs_sedi, al_giorno=date.today()):
    from formazione.models import Corso
    return [
        (COMPLETO,  Corso.objects.filter(sede__in=qs_sedi)),
    ] \
        + espandi_gestione_corso(Corso.objects.filter(sede__in=qs_sedi))

def espandi_gestione_corso(qs_corsi, al_giorno=date.today()):
    from anagrafica.models import Persona
    return [
        (MODIFICA,  qs_corsi),
        (MODIFICA,  Persona.objects.filter(partecipazioni_corsi__corso__in=qs_corsi)).exclude(aspirante__id__innull=True),
        (LETTURA,   Persona.objects.filter(partecipazioni_corsi__corso__in=qs_corsi)),
    ]


ESPANDI_PERMESSI = {
    GESTIONE_SOCI:          espandi_gestione_soci,
    ELENCHI_SOCI:           espandi_elenchi_soci,
    GESTIONE_SEDE:          espandi_gestione_sede,
    GESTIONE_ATTIVITA_SEDE: espandi_gestione_attivita_sede,
    GESTIONE_ATTIVITA_AREA: espandi_gestione_attivita_area,
    GESTIONE_ATTIVITA:      espandi_gestione_attivita,
    GESTIONE_CORSI_SEDE:    espandi_gestione_corsi_sede,
    GESTIONE_CORSO:         espandi_gestione_corso,
}