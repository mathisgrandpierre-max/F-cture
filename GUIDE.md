# Elixir Signature — Guide complet

> Le code de la page d'accueil est dans `index.html` (double-clic pour l'ouvrir dans votre navigateur).
> Les prix, textes et tarifs ci-dessous sont indicatifs : vérifiez-les avant de vous engager.

## 1. Direction artistique

**Palette** (uniquement ces 4 couleurs ; un *code hexadécimal* est le code à 6 caractères qui désigne une couleur) :

| Rôle | Couleur | Code |
|---|---|---|
| Fond principal | Noir profond | `#0A0A0A` |
| Fond des cartes | Noir adouci | `#141311` |
| Accent (titres, boutons, filets) | Or | `#C9A24B` |
| Reflet au survol | Or clair | `#E3C77A` |
| Texte | Blanc cassé | `#F2EDE4` |

**Polices** (Google Fonts, gratuites) : **Great Vibes** (signature manuscrite : logo et titres) + **Montserrat** (texte, graisse légère, lisible et masculine).

**Boutons** : rectangulaires, angles droits, cadre doré fin, majuscules espacées. Au survol, ils se remplissent d'or avec un halo lumineux.

**Images** : flacons photographiés sur fond noir, lumière latérale chaude, reflets dorés, beaucoup de vide autour. Pas de sourires publicitaires : mains, ombres, matières (cuir, bois, pierre).

**Animations** : lentes et discrètes (apparition progressive de 1 s, légère montée de 6 px au survol). Rien qui clignote.

## 2. Architecture du site

1. **Accueil** : hero, marque, collection, histoire, newsletter (fait).
2. **Collection** : les 3 parfums côte à côte, filtres plus tard.
3. **Fiche produit** : grande photo, description, notes tête/cœur/fond, contenance, prix, « Ajouter au panier », avis.
4. **Notre histoire** : la marque, la philosophie « signature ».
5. **Contact** : formulaire + e-mail + réseaux.
6. **Panier** : récapitulatif, code promo, paiement sécurisé.

## 3. Textes

**Slogan** : « Laissez votre signature. » (variantes : « Ce que vous laissez derrière vous. » / « Votre sillage vous précède. »)

**Marque** : *Elixir Signature est née d'une conviction : un homme ne se reconnaît pas à ce qu'il dit, mais à ce qu'il laisse derrière lui. Chaque fragrance est composée comme une écriture : des notes franches, un sillage maîtrisé, aucune concession.*

| Parfum | Ambiance | Tête | Cœur | Fond |
|---|---|---|---|---|
| **Mila** | Boisé, ambré, magnétique. Une chaleur élégante et enveloppante. | Bergamote, poivre rose | Iris, cèdre | Ambre, vanille noire, tonka |
| **Blanche Bête** | Frais, sauvage, puissant. Un contraste glacé et animal. | Menthe poivrée, genévrier | Sauge, lavande noire | Musc blanc, vétiver, cuir |
| **Delta** | Oriental, épicé, nocturne. Profond et fumé. | Cardamome, safran | Encens, cuir | Oud, patchouli, résine d'ambre |

*Notes de tête* = ce qu'on sent dans les premières minutes. *Notes de cœur* = le caractère, quelques heures. *Notes de fond* = le sillage qui reste.

Descriptions complètes : dans `index.html`, section « A. DONNÉES DES PRODUITS ».

## 4. Mise en ligne (gratuit ou peu cher)

*Hébergement* = l'ordinateur permanent qui affiche votre site 24 h/24.

**Montrer le site (vitrine) gratuitement** : **Netlify Drop** (netlify.com/drop : glissez le dossier, le site est en ligne en 30 secondes), **GitHub Pages** ou **Cloudflare Pages**. Gratuit, rapide, HTTPS (cadenas de sécurité) inclus.

**Vendre dès le lancement : trois options**

| Option | Avantages | Coûts approximatifs | Pour vous ? |
|---|---|---|---|
| **Shopify** | Tout-en-un : paiement, stocks, livraison, TVA. Prêt en 1 jour, aucune compétence technique. | Abonnement ~25-30 €/mois (essai à 1 €/mois les premiers mois) + ~2 % de frais de paiement + ~0,25 € par vente | **Recommandé** pour débuter |
| **WooCommerce** (extension WordPress) | Gratuit en logiciel, très flexible, vous possédez tout. | Hébergement 5-15 €/mois + domaine + extensions. Plus de maintenance (mises à jour, sécurité). | Si vous êtes à l'aise avec la technique |
| **Sur mesure** | Contrôle total sur le design. | Développeur : plusieurs milliers d'euros, ou paiement via **Stripe Payment Links** (liens de paiement, ~1,5 % + 0,25 €) | Trop lourd au lancement |

**Plan malin** : créez la boutique sur Shopify avec un thème sombre, collez-y vos textes et couleurs (or `#C9A24B`, noir `#0A0A0A`, Great Vibes), et utilisez `index.html` comme maquette de référence. Alternative ultra-légère : gardez `index.html` et remplacez le bouton « Commander » par un lien Stripe Payment Link.

**Nom de domaine** (l'adresse du site) : ~10-15 €/an chez OVH, Gandi ou Namecheap. Visez `elixir-signature.fr` ; vérifiez la disponibilité et le nom sur le registre INPI.

## 5. Conseils de base

**SEO** (apparaître sur Google) : un titre et une description clairs par page (déjà dans le fichier) ; mots-clés naturels (« parfum homme boisé », « parfum homme oriental ») ; descriptions de produits uniques ; images avec texte alternatif ; site rapide et mobile ; fiche Google Business, Instagram et TikTok liés au site.

**Photos des flacons** : fond noir uni, lumière douce latérale, reflet au sol, 3 angles + 1 photo « matière ». Un smartphone récent + lampe + carton noir suffisent au début. Format WebP, moins de 300 Ko par image.

**Obligations françaises** (à valider auprès d'un professionnel ; ceci n'est pas un conseil juridique) :
- **Statut** : micro-entrepreneur (ex auto-entrepreneur) sur autoentrepreneur.urssaf.fr, gratuit, plafond de CA ~188 700 € pour la vente de marchandises (vérifier le plafond en vigueur) ; franchise de TVA possible sous le seuil.
- **Mentions légales** : identité, SIRET, adresse, e-mail, hébergeur du site, directeur de publication.
- **CGV** (conditions générales de vente) : prix TTC, livraison, paiement, **droit de rétractation de 14 jours** (exception : produit descellé pour raison d'hygiène, à préciser), garantie légale, médiateur de la consommation (obligatoire).
- **RGPD** (protection des données) : politique de confidentialité, consentement clair pour la newsletter, bandeau cookies si traceurs, droit d'accès et de suppression.
- **Étiquetage cosmétique** (règlement européen CE 1223/2009) : nom et adresse du responsable de mise sur le marché, contenance, liste INCI des ingrédients, allergènes à déclarer, numéro de lot, durée de vie (PAO), pictogrammes de danger (inflammable). Un **dossier d'information produit** et un **rapport de sécurité** par un évaluateur qualifié sont obligatoires, ainsi qu'une **notification sur le portail européen CPNP** avant la vente. Fabriquer via un laboratoire de sous-traitance qualifié simplifie beaucoup ces démarches.
- **Transport** : les parfums contiennent de l'alcool (inflammable) : vérifiez les règles des transporteurs.

## 6. Mes 3 actions à faire cette semaine

1. **Ouvrir `index.html`** dans votre navigateur, modifier vos textes, et le mettre en ligne sur Netlify Drop pour avoir une vitrine visible.
2. **Créer votre statut de micro-entrepreneur** et réserver votre nom de domaine `elixir-signature.fr`.
3. **Ouvrir l'essai Shopify**, ajouter les 3 parfums à 39,99 €, et contacter un laboratoire pour valider conformité et étiquetage avant la première vente.
