<?php
if ( ! defined( 'ABSPATH' ) ) {
	exit;
}

class BNN_Intel_Public {

	const SHORTCODES = array( 'ranking', 'official', 'countries', 'country', 'category', 'compare', 'incidents', 'methodology' );

	public static function init() {
		add_action( 'init', array( __CLASS__, 'add_rewrite' ) );
		add_filter( 'query_vars', fn( $v ) => array_merge( $v, array( 'bnn_country' ) ) );
		add_action( 'rest_api_init', array( __CLASS__, 'routes' ) );
		add_action( 'wp_enqueue_scripts', array( __CLASS__, 'register_assets' ) );
		add_filter( 'template_include', array( __CLASS__, 'country_template' ) );
		add_filter( 'pre_get_document_title', array( __CLASS__, 'country_title' ), 20 );
		// Full-width, no sidebar on the generated country pages (Astra and most themes).
		add_filter( 'astra_page_layout', fn( $l ) => get_query_var( 'bnn_country' ) ? 'no-sidebar' : $l, 20 );
		add_filter( 'astra_get_content_layout', fn( $l ) => get_query_var( 'bnn_country' ) ? 'plain-container' : $l, 20 );
		add_filter( 'body_class', fn( $c ) => get_query_var( 'bnn_country' ) ? array_merge( $c, array( 'bnn-intel-country' ) ) : $c );
		foreach ( self::SHORTCODES as $sc ) {
			add_shortcode( 'bnn_intel_' . $sc, function ( $atts ) use ( $sc ) {
				return BNN_Intel_Public::render( $sc, (array) $atts );
			} );
		}
	}

	public static function add_rewrite() {
		$base = BNN_Intel_API::settings()['country_base'];
		add_rewrite_rule( '^' . preg_quote( $base, '#' ) . '/([a-z0-9-]+)/?$', 'index.php?bnn_country=$matches[1]', 'top' );
	}

	/** Public proxy: /wp-json/bnn-intel/v1/data?path=ranking/&category=… (whitelisted, cached). */
	public static function routes() {
		register_rest_route( 'bnn-intel/v1', '/data', array(
			'methods'             => 'GET',
			'permission_callback' => '__return_true',
			'callback'            => function ( WP_REST_Request $r ) {
				$params = $r->get_query_params();
				$path   = $params['path'] ?? '';
				unset( $params['path'] );
				$data = BNN_Intel_API::get( $path, $params );
				if ( is_wp_error( $data ) ) {
					return new WP_REST_Response( array( 'error' => 'Data temporarily unavailable.' ), 503 );
				}
				$res = new WP_REST_Response( $data );
				$res->header( 'Cache-Control', 'public, max-age=300' );
				return $res;
			},
		) );
	}

	public static function register_assets() {
		wp_register_style( 'bnn-intel', BNN_INTEL_URL . 'assets/bnn-intel.css', array(), BNN_INTEL_VERSION );
		wp_register_script( 'bnn-intel', BNN_INTEL_URL . 'assets/bnn-intel.js', array(), BNN_INTEL_VERSION, array( 'in_footer' => true, 'strategy' => 'defer' ) );
		wp_localize_script( 'bnn-intel', 'BNN_INTEL', array(
			'endpoint'    => esc_url_raw( rest_url( 'bnn-intel/v1/data' ) ),
			'countryBase' => home_url( '/' . BNN_Intel_API::settings()['country_base'] . '/' ),
			'apiPublic'   => esc_url_raw( BNN_Intel_API::settings()['api_base'] ),
		) );
	}

	/** Shortcode → container + server-rendered fallback (so content is indexable and works without JS). */
	public static function render( $type, $atts ) {
		wp_enqueue_style( 'bnn-intel' );
		wp_enqueue_script( 'bnn-intel' );
		$atts = array_map( 'sanitize_text_field', $atts );
		if ( 'country' === $type && empty( $atts['slug'] ) ) {
			$atts['slug'] = sanitize_title( get_query_var( 'bnn_country' ) );
		}
		$attr = '';
		foreach ( $atts as $k => $v ) {
			$attr .= ' data-' . esc_attr( sanitize_key( $k ) ) . '="' . esc_attr( $v ) . '"';
		}
		return '<div class="bnn-intel" data-bnn="' . esc_attr( $type ) . '"' . $attr . '>' . self::fallback( $type, $atts ) . '</div>';
	}

	/** Minimal server-side HTML (SEO + no-JS). JS replaces it with the interactive view. */
	private static function fallback( $type, $atts ) {
		$out = '<noscript><p>Enable JavaScript for the interactive view.</p></noscript>';
		if ( 'ranking' === $type ) {
			$d = BNN_Intel_API::get( 'ranking/', array_filter( array( 'category' => $atts['category'] ?? '' ) ) );
			if ( is_wp_error( $d ) ) {
				return $out . '<p class="bnn-i-muted">Ranking data is temporarily unavailable.</p>';
			}
			if ( empty( $d['results'] ) ) {
				return $out . '<p class="bnn-i-muted">' . esc_html( $d['message'] ?? 'No published ranking yet.' ) . '</p>';
			}
			$out .= '<ol class="bnn-i-fallback">';
			foreach ( array_slice( $d['results'], 0, 60 ) as $r ) {
				$out .= '<li>' . esc_html( $r['country']['name'] ) . ' – ' . ( $r['is_ranked'] ? esc_html( number_format( (float) $r['score'], 1 ) ) : esc_html( $r['status_label'] ) ) . '</li>';
			}
			return $out . '</ol>';
		}
		if ( 'countries' === $type ) {
			$d = BNN_Intel_API::get( 'countries/' );
			if ( is_wp_error( $d ) ) {
				return $out;
			}
			$base = home_url( '/' . BNN_Intel_API::settings()['country_base'] . '/' );
			$out .= '<ul class="bnn-i-fallback">';
			foreach ( $d as $c ) {
				$out .= '<li><a href="' . esc_url( $base . $c['slug'] . '/' ) . '">' . esc_html( $c['name'] ) . '</a></li>';
			}
			return $out . '</ul>';
		}
		if ( 'country' === $type && ! empty( $atts['slug'] ) ) {
			$d = BNN_Intel_API::get( 'countries/' . $atts['slug'] . '/profile/' );
			if ( is_wp_error( $d ) ) {
				return $out;
			}
			$out .= '<h2>' . esc_html( $d['country']['name'] ) . '</h2><ul class="bnn-i-fallback">';
			foreach ( $d['observations'] as $o ) {
				if ( $o['is_historical'] ) {
					continue;
				}
				$out .= '<li>' . esc_html( $o['indicator_name'] . ': ' . $o['value'] . ' (' . $o['reference_label'] . ', ' . $o['source'] . ')' ) . '</li>';
			}
			return $out . '</ul>';
		}
		return $out . '<div class="bnn-i-skeleton"></div>';
	}

	public static function country_template( $template ) {
		$slug = get_query_var( 'bnn_country' );
		if ( ! $slug ) {
			return $template;
		}
		$d = BNN_Intel_API::get( 'countries/' . sanitize_title( $slug ) . '/profile/' );
		if ( is_wp_error( $d ) || empty( $d['country'] ) ) {
			global $wp_query;
			$wp_query->set_404();
			status_header( 404 );
			return get_404_template();
		}
		return __DIR__ . '/../templates/country.php';
	}

	public static function country_title( $title ) {
		$slug = get_query_var( 'bnn_country' );
		if ( ! $slug ) {
			return $title;
		}
		$d = BNN_Intel_API::get( 'countries/' . sanitize_title( $slug ) . '/profile/' );
		return is_wp_error( $d ) ? $title : $d['country']['name'] . ' – Country Intelligence ' . $d['period']['name'] . ' | BNN Asia';
	}
}
